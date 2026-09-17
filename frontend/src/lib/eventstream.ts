// AWS event-stream binary framing used by Amazon Transcribe streaming over WebSocket.
const CRC_TABLE = (() => {
  const t = new Uint32Array(256);
  for (let n = 0; n < 256; n++) {
    let c = n;
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    t[n] = c >>> 0;
  }
  return t;
})();

export function crc32(bytes: Uint8Array, start = 0, end = bytes.length): number {
  let c = 0xffffffff;
  for (let i = start; i < end; i++) c = CRC_TABLE[(c ^ bytes[i]) & 0xff] ^ (c >>> 8);
  return (c ^ 0xffffffff) >>> 0;
}

const enc = new TextEncoder();
const dec = new TextDecoder();

export function encodeMessage(headers: Record<string, string>, payload: Uint8Array): Uint8Array<ArrayBuffer> {
  const headerParts: Uint8Array[] = [];
  for (const [name, value] of Object.entries(headers)) {
    const n = enc.encode(name);
    const v = enc.encode(value);
    const part = new Uint8Array(1 + n.length + 1 + 2 + v.length);
    const dv = new DataView(part.buffer);
    part[0] = n.length;
    part.set(n, 1);
    part[1 + n.length] = 7; // string
    dv.setUint16(2 + n.length, v.length);
    part.set(v, 4 + n.length);
    headerParts.push(part);
  }
  const headersLen = headerParts.reduce((s, p) => s + p.length, 0);
  const total = 12 + headersLen + payload.length + 4;
  const out = new Uint8Array(total);
  const dv = new DataView(out.buffer);
  dv.setUint32(0, total);
  dv.setUint32(4, headersLen);
  dv.setUint32(8, crc32(out, 0, 8));
  let off = 12;
  for (const p of headerParts) {
    out.set(p, off);
    off += p.length;
  }
  out.set(payload, off);
  dv.setUint32(total - 4, crc32(out, 0, total - 4));
  return out;
}

export type DecodedMessage = { headers: Record<string, string>; payload: Uint8Array };

export function decodeMessage(buf: Uint8Array): DecodedMessage {
  const dv = new DataView(buf.buffer, buf.byteOffset, buf.byteLength);
  const total = dv.getUint32(0);
  const headersLen = dv.getUint32(4);
  if (total !== buf.byteLength) throw new Error("event-stream length mismatch");
  if (dv.getUint32(8) !== crc32(buf, 0, 8)) throw new Error("event-stream prelude crc mismatch");
  if (dv.getUint32(total - 4) !== crc32(buf, 0, total - 4)) throw new Error("event-stream message crc mismatch");
  const headers: Record<string, string> = {};
  let off = 12;
  const end = 12 + headersLen;
  while (off < end) {
    const nameLen = buf[off];
    const name = dec.decode(buf.subarray(off + 1, off + 1 + nameLen));
    off += 1 + nameLen;
    const type = buf[off];
    off += 1;
    if (type === 7 || type === 6) {
      const len = dv.getUint16(off);
      off += 2;
      headers[name] = dec.decode(buf.subarray(off, off + len));
      off += len;
    } else {
      throw new Error(`unsupported header type ${type}`);
    }
  }
  return { headers, payload: buf.subarray(end, total - 4) };
}

export function audioEvent(pcm: Uint8Array): Uint8Array<ArrayBuffer> {
  return encodeMessage({ ":content-type": "application/octet-stream", ":event-type": "AudioEvent", ":message-type": "event" }, pcm);
}
