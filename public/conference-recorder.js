// AudioWorklet keeps capture off the UI thread. Output is always silent.
class ConferenceRecorder extends AudioWorkletProcessor {
  constructor() {
    super(); this.parts=[]; this.length=0;
    this.port.onmessage=(event)=>{if(event.data==='flush'){this.flush();this.port.postMessage({flushed:true});}};
  }
  flush(){
    if(!this.length)return;
    const samples=new Float32Array(this.length);let offset=0;
    for(const part of this.parts){samples.set(part,offset);offset+=part.length;}
    this.parts=[];this.length=0;this.port.postMessage({samples},[samples.buffer]);
  }
  process(inputs){
    const input=inputs[0]?.[0];
    if(input){this.parts.push(input.slice());this.length+=input.length;if(this.length>=sampleRate*8)this.flush();}
    return true;
  }
}
registerProcessor('conference-recorder',ConferenceRecorder);
