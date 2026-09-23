export type RemotePeer = {
  id: string;
  name: string;
  stream: MediaStream;
  state: RTCPeerConnectionState;
  muted: boolean;
  camera: boolean;
  sharing: boolean;
};
type Peer = RemotePeer & {
  pc: RTCPeerConnection;
  makingOffer: boolean;
  ignoreOffer: boolean;
  settingAnswer: boolean;
  candidates: RTCIceCandidateInit[];
};
type CallEvents = {
  peers: (p: RemotePeer[]) => void;
  status: (s: string) => void;
  changed: () => void;
  ended: () => void;
  error: (e: string) => void;
  local: (s: MediaStream) => void;
};

export class ConferenceCall {
  stream = new MediaStream();
  audioContext: AudioContext | null = null;
  socket: WebSocket | null = null;
  private peers = new Map<string, Peer>();
  private closed = false;
  private reconnect: ReturnType<typeof setTimeout> | undefined;
  private heartbeat: ReturnType<typeof setInterval> | undefined;
  private attempts = 0;
  private cameraTrack: MediaStreamTrack | null = null;
  private screenTrack: MediaStreamTrack | null = null;
  private self = "";
  private messages = Promise.resolve();
  muted = false;
  camera = false;
  sharing = false;
  constructor(
    private room: string,
    private token: string,
    private iceServers: RTCIceServer[],
    private events: CallEvents,
  ) {}

  async start(camera = false) {
    if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia)
      throw new Error(
        "Для микрофона нужен HTTPS с доверенным сертификатом. Откройте LAN-ссылку из инструкции запуска.",
      );
    this.audioContext = new AudioContext();
    await this.audioContext.resume();
    try {
      this.stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
          channelCount: 1,
        },
        video: camera,
      });
      if (this.closed) {
        this.stream.getTracks().forEach((t) => t.stop());
        return;
      }
      this.cameraTrack = this.stream.getVideoTracks()[0] || null;
      this.camera = !!this.cameraTrack;
      this.events.local(new MediaStream(this.stream.getTracks()));
      this.connect();
    } catch (error) {
      await this.audioContext.close();
      this.audioContext = null;
      throw error;
    }
  }
  private send(message: unknown) {
    if (this.socket?.readyState === WebSocket.OPEN)
      this.socket.send(JSON.stringify(message));
  }
  private publish() {
    this.events.peers(
      [...this.peers.values()].map(
        ({ id, name, stream, state, muted, camera, sharing }) => ({
          id,
          name,
          stream,
          state,
          muted,
          camera,
          sharing,
        }),
      ),
    );
  }
  private connect() {
    if (this.closed) return;
    this.events.status(this.attempts ? "reconnecting" : "connecting");
    const socket = new WebSocket(
      `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/api/v1/conferences/${this.room}/ws`,
    );
    this.socket = socket;
    socket.onopen = () => this.send({ type: "auth", token: this.token });
    socket.onmessage = (event) => {
      this.messages = this.messages
        .then(async () => {
          if (this.closed || this.socket !== socket) return;
          const message = JSON.parse(event.data);
          if (message.type === "welcome") {
            this.self = message.self;
            this.attempts = 0;
            for (const p of message.peers) this.ensurePeer(p.id, p.name, p);
            this.events.status("connected");
            this.mediaState();
            this.events.changed();
            clearInterval(this.heartbeat);
            this.heartbeat = setInterval(
              () => this.send({ type: "ping" }),
              20000,
            );
          } else if (message.type === "peer-joined") {
            this.ensurePeer(message.id, message.name);
            this.events.changed();
          } else if (message.type === "peer-left") {
            this.removePeer(message.id);
            this.events.changed();
          } else if (message.type === "media") {
            const peer = this.peers.get(message.id);
            if (peer) {
              Object.assign(peer, {
                muted: message.muted,
                camera: message.camera,
                sharing: message.sharing,
              });
              this.publish();
            }
          } else if (message.type === "signal") {
            await this.signal(message.from, message.data);
          } else if (message.type === "ended") {
            this.events.ended();
          } else if (message.type === "room-updated") this.events.changed();
        })
        .catch(() =>
          this.events.error(
            "Не удалось согласовать медиасоединение. Перезайдите в конференцию.",
          ),
        );
    };
    socket.onclose = (event) => {
      clearInterval(this.heartbeat);
      for (const id of [...this.peers.keys()]) this.removePeer(id);
      if (this.closed) return;
      if ([4000, 4004, 4009, 1008].includes(event.code)) {
        this.events.error(
          event.reason ||
            "Подключение отклонено. Обновите приглашение или войдите снова.",
        );
        this.events.status("disconnected");
        this.leave();
        return;
      }
      this.events.status("reconnecting");
      this.reconnect = setTimeout(
        () => this.connect(),
        Math.min(1000 * 2 ** this.attempts++, 10000),
      );
    };
  }
  private ensurePeer(
    id: string,
    name: string,
    media?: Partial<RemotePeer>,
  ): Peer {
    const existing = this.peers.get(id);
    if (existing) return existing;
    const pc = new RTCPeerConnection({ iceServers: this.iceServers });
    const peer: Peer = {
      id,
      name,
      pc,
      stream: new MediaStream(),
      state: "new",
      muted: media?.muted || false,
      camera: media?.camera || false,
      sharing: media?.sharing || false,
      makingOffer: false,
      ignoreOffer: false,
      settingAnswer: false,
      candidates: [],
    };
    this.peers.set(id, peer);
    pc.addTransceiver(this.stream.getAudioTracks()[0] || "audio", {
      direction: "sendrecv",
      streams: [this.stream],
    });
    pc.addTransceiver(this.screenTrack || this.cameraTrack || "video", {
      direction: "sendrecv",
      streams: [this.stream],
    });
    pc.ontrack = (event) => {
      peer.stream.addTrack(event.track);
      event.track.onunmute = () => this.publish();
      event.track.onended = () => {
        peer.stream.removeTrack(event.track);
        this.publish();
      };
      this.publish();
    };
    pc.onicecandidate = ({ candidate }) => {
      if (candidate)
        this.send({
          type: "signal",
          to: id,
          data: { candidate: candidate.toJSON() },
        });
    };
    pc.onconnectionstatechange = () => {
      peer.state = pc.connectionState;
      this.publish();
    };
    pc.oniceconnectionstatechange = () => {
      if (
        pc.iceConnectionState === "failed" &&
        this.socket?.readyState === WebSocket.OPEN
      )
        pc.restartIce();
    };
    pc.onnegotiationneeded = async () => {
      try {
        peer.makingOffer = true;
        await pc.setLocalDescription();
        this.send({
          type: "signal",
          to: id,
          data: { description: pc.localDescription },
        });
      } catch {
        if (!this.closed)
          this.events.error(
            "Не удалось начать передачу медиа. Проверьте разрешения и сеть.",
          );
      } finally {
        peer.makingOffer = false;
      }
    };
    this.publish();
    return peer;
  }
  private async signal(
    id: string,
    data: {
      description?: RTCSessionDescriptionInit;
      candidate?: RTCIceCandidateInit;
    },
  ) {
    const peer = this.peers.get(id);
    if (!peer || !data) return;
    const pc = peer.pc;
    if (data.description) {
      const ready =
        !peer.makingOffer &&
        (pc.signalingState === "stable" || peer.settingAnswer);
      const collision = data.description.type === "offer" && !ready;
      const polite = this.self.localeCompare(id) > 0;
      peer.ignoreOffer = !polite && collision;
      if (peer.ignoreOffer) {
        peer.candidates = [];
        return;
      }
      peer.settingAnswer = data.description.type === "answer";
      try {
        await pc.setRemoteDescription(data.description);
      } finally {
        peer.settingAnswer = false;
      }
      for (const candidate of peer.candidates.splice(0))
        await pc.addIceCandidate(candidate);
      if (data.description.type === "offer") {
        await pc.setLocalDescription();
        this.send({
          type: "signal",
          to: id,
          data: { description: pc.localDescription },
        });
      }
    } else if (data.candidate && !peer.ignoreOffer) {
      if (pc.remoteDescription) await pc.addIceCandidate(data.candidate);
      else peer.candidates.push(data.candidate);
    }
  }
  private removePeer(id: string) {
    const p = this.peers.get(id);
    if (p) {
      p.pc.close();
      this.peers.delete(id);
      this.publish();
    }
  }
  private mediaState() {
    this.send({
      type: "media",
      muted: this.muted,
      camera: this.camera,
      sharing: this.sharing,
    });
  }
  toggleMic() {
    this.muted = !this.muted;
    this.stream.getAudioTracks().forEach((t) => (t.enabled = !this.muted));
    this.mediaState();
  }
  async toggleCamera() {
    if (this.cameraTrack) {
      this.cameraTrack.stop();
      this.stream.removeTrack(this.cameraTrack);
      this.cameraTrack = null;
      this.camera = false;
    } else {
      const camera = await navigator.mediaDevices.getUserMedia({ video: true });
      this.cameraTrack = camera.getVideoTracks()[0];
      this.stream.addTrack(this.cameraTrack);
      this.camera = true;
    }
    if (!this.sharing) await this.replaceVideo(this.cameraTrack);
    this.events.local(new MediaStream(this.stream.getTracks()));
    this.mediaState();
  }
  private async replaceVideo(track: MediaStreamTrack | null) {
    await Promise.all(
      [...this.peers.values()].map((p) =>
        p.pc
          .getTransceivers()
          .find((t) => t.receiver.track.kind === "video")
          ?.sender.replaceTrack(track),
      ),
    );
  }
  async shareScreen() {
    if (this.screenTrack) {
      this.screenTrack.stop();
      await this.stopShare();
      return;
    }
    const display = await navigator.mediaDevices.getDisplayMedia({
      video: true,
      audio: false,
    });
    this.screenTrack = display.getVideoTracks()[0];
    this.sharing = true;
    this.screenTrack.onended = () => void this.stopShare();
    await this.replaceVideo(this.screenTrack);
    this.events.local(
      new MediaStream([...this.stream.getAudioTracks(), this.screenTrack]),
    );
    this.mediaState();
  }
  private async stopShare() {
    this.screenTrack = null;
    this.sharing = false;
    await this.replaceVideo(this.cameraTrack);
    this.events.local(new MediaStream(this.stream.getTracks()));
    this.mediaState();
  }
  chat(text: string) {
    if (this.socket?.readyState !== WebSocket.OPEN)
      throw new Error("Чат недоступен: восстанавливается соединение.");
    this.send({ type: "chat", text });
  }
  leave() {
    this.closed = true;
    clearTimeout(this.reconnect);
    clearInterval(this.heartbeat);
    this.socket?.close();
    for (const id of [...this.peers.keys()]) this.removePeer(id);
    this.stream.getTracks().forEach((t) => t.stop());
    this.screenTrack?.stop();
    void this.audioContext?.close();
  }
}
