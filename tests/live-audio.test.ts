import assert from 'node:assert/strict';
import test from 'node:test';
import {encodeWave, LiveCapture} from '../lib/live-audio';

test('PCM WAV preserves duration, sample rate, sign and saturates loud samples', async () => {
  const input = new Float32Array(48000);
  input.fill(2, 0, 24000); input.fill(-2, 24000);
  const wave = await encodeWave(input, 48000).arrayBuffer();
  const view = new DataView(wave);
  assert.equal(new TextDecoder().decode(wave.slice(0,4)), 'RIFF');
  assert.equal(view.getUint32(24,true),16000);
  assert.equal(view.getUint16(22,true),1);
  assert.equal(view.getUint32(40,true),32000);
  assert.equal(view.getInt16(44,true),32767);
  assert.equal(view.getInt16(44+16000,true),-32768);
});

test('overlapping stop requests flush the last chunk once before resolving', async () => {
  let disconnects=0, uploads=0;
  const original = globalThis.AudioWorkletNode;
  class Node {
    port = {
      onmessage: null as null | ((event: {data: unknown}) => void),
      postMessage: () => queueMicrotask(() => {
        this.port.onmessage?.({data:{samples:new Float32Array(1600).fill(.25)}});
        this.port.onmessage?.({data:{flushed:true}});
      }),
      close() {},
    };
    connect() {} disconnect() {disconnects++;}
  }
  globalThis.AudioWorkletNode = Node as unknown as typeof AudioWorkletNode;
  try {
    const context = {state:'running',sampleRate:16000,destination:{},audioWorklet:{addModule:async()=>{}},createMediaStreamSource:()=>({connect(){},disconnect(){}})};
    const queue = {add:async(blob:Blob,start:number,version:number)=>{
      assert.equal(blob.size,3244); assert.equal(start,12); assert.equal(version,2);
      await new Promise(resolve=>setTimeout(resolve,5)); uploads++;
    }};
    const capture = new LiveCapture(context as unknown as AudioContext, {} as MediaStream,12,2,queue as never,assert.fail);
    await capture.begin();
    await Promise.all([capture.stop(),capture.stop()]);
    assert.equal(uploads,1); assert.equal(disconnects,1);
  } finally { globalThis.AudioWorkletNode=original; }
});
