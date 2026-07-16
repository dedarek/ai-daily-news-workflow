#!/usr/bin/env node
import { createCipheriv, createHash, createHmac, randomBytes, scryptSync } from "node:crypto";
import { promises as fs } from "node:fs";
import path from "node:path";

const SCRYPT_OPTS = { N: 1 << 15, r: 8, p: 1, maxmem: 128 * 1024 * 1024 };

function parseArgs() {
  const args = {};
  for (let index = 2; index < process.argv.length; index += 1) {
    const item = process.argv[index];
    if (!item.startsWith("--")) continue;
    const key = item.slice(2);
    const next = process.argv[index + 1];
    if (!next || next.startsWith("--")) {
      args[key] = "true";
    } else {
      args[key] = next;
      index += 1;
    }
  }
  return args;
}

function required(args, key) {
  const value = args[key];
  if (!value) throw new Error(`--${key} is required`);
  return value;
}

function hashApiId(apiKey) {
  return createHash("sha256").update(apiKey).digest("hex").slice(0, 16);
}

function deriveKey(apiKey, apiKeyId) {
  return scryptSync(
    apiKey,
    createHash("sha256").update(`ai-daily:${apiKeyId}`).digest(),
    32,
    SCRYPT_OPTS,
  );
}

function hkdf(material, info) {
  return createHmac("sha256", Buffer.alloc(32))
    .update(material)
    .update(Buffer.from([0x01]))
    .update(Buffer.from(info))
    .digest()
    .subarray(0, 32);
}

function encrypt(plain, key) {
  const iv = randomBytes(12);
  const cipher = createCipheriv("aes-256-gcm", key, iv);
  const ct = Buffer.concat([cipher.update(plain), cipher.final()]);
  return { iv, tag: cipher.getAuthTag(), ct };
}

function hmacSign(data, key) {
  return createHmac("sha256", key).update(data).digest("hex");
}

function displayDate(date) {
  const [year, month, day] = date.split("-");
  return `${year}年${month}月${day}日`;
}

function weekday(date) {
  return ["周日", "周一", "周二", "周三", "周四", "周五", "周六"][
    new Date(`${date}T00:00:00+08:00`).getDay()
  ];
}

async function readMedia(file) {
  if (!file) return null;
  const data = await fs.readFile(file);
  const ext = path.extname(file).slice(1).toLowerCase();
  const mime = ["mp3", "wav", "m4a"].includes(ext)
    ? `audio/${ext === "mp3" ? "mpeg" : ext}`
    : ["mp4", "webm", "mov"].includes(ext)
      ? `video/${ext}`
      : "application/octet-stream";
  return { name: path.basename(file), mime, data: data.toString("base64"), bytes: data.length };
}

function parseNewsText(raw) {
  const lines = raw.split(/\r?\n/);
  const items = [];
  let current = null;
  let comment = "";
  let collectingComment = false;
  let position = 0;
  let activeCategory = "焦点";

  const flush = () => {
    if (!current || (!current.summary && !comment)) return;
    items.push({
      position,
      category: current.category,
      title: current.title,
      summary: current.summary || "",
      url: current.url || null,
      comment: comment || null,
    });
    position += 1;
  };

  for (const rawLine of lines) {
    const line = rawLine.trim();
    if (!line) {
      flush();
      current = null;
      comment = "";
      collectingComment = false;
      continue;
    }
    if (/^[🔥🚀💼💡🔓🤖💰]/u.test(line) || /^今日/.test(line)) {
      flush();
      activeCategory = line.replace(/^[🔥🚀💼💡🔓🤖💰]\s*/u, "").trim() || activeCategory;
      current = null;
      comment = "";
      collectingComment = false;
      continue;
    }
    const reviewMatch = line.match(/^AI锐评[：:]\s*(.*)$/);
    if (reviewMatch) {
      collectingComment = true;
      comment = reviewMatch[1].trim();
      continue;
    }
    if (line.startsWith("🔗")) {
      if (current) current.url = line.replace(/^🔗\s*/, "").trim();
      collectingComment = false;
      continue;
    }
    if (!current) {
      current = { title: line, category: activeCategory, summary: "" };
    } else if (collectingComment) {
      comment = comment ? `${comment} ${line}` : line;
    } else {
      current.summary = current.summary ? `${current.summary}\n${line}` : line;
    }
  }
  flush();
  return { intro: lines[0] || "", items };
}

async function main() {
  const args = parseArgs();
  const apiKey = process.env.AI_DAILY_NEW_SITE_API_KEY;
  if (!apiKey) throw new Error("AI_DAILY_NEW_SITE_API_KEY is required");

  const date = required(args, "date");
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) throw new Error("--date must be YYYY-MM-DD");
  const endpoint = (args.endpoint || process.env.AI_DAILY_NEW_SITE_ENDPOINT || "http://47.108.192.42:4000/daily").replace(/\/$/, "");
  const txtPath = required(args, "txt");
  const outDir = path.resolve(args["out-dir"] || ".");
  await fs.mkdir(outDir, { recursive: true });

  const raw = await fs.readFile(txtPath, "utf8");
  const parsed = parseNewsText(raw);
  const audio = await readMedia(args.audio);
  const video = await readMedia(args.video);
  const payload = {
    date,
    title: args.title || `AI 晚报：${date} 行业要闻速览`,
    intro: parsed.intro,
    weekday: weekday(date),
    displayDate: displayDate(date),
    audio,
    video,
    items: parsed.items,
  };

  const plain = Buffer.from(JSON.stringify(payload), "utf8");
  const apiKeyId = hashApiId(apiKey);
  const material = deriveKey(apiKey, apiKeyId);
  const encKey = hkdf(material, "enc");
  const macKey = hkdf(material, "mac");
  const { iv, tag, ct } = encrypt(plain, encKey);
  const ts = Date.now().toString();
  const nonce = randomBytes(16).toString("hex");
  const signature = hmacSign(
    `${apiKeyId}|${ts}|${nonce}|${iv.toString("base64")}|${ct.toString("base64")}|${tag.toString("base64")}`,
    macKey,
  );
  const body = JSON.stringify({
    v: 1,
    apiKeyId,
    ts,
    nonce,
    iv: iv.toString("base64"),
    tag: tag.toString("base64"),
    ct: ct.toString("base64"),
  });
  const headers = {
    url: `${endpoint}/api/upload`,
    apiKeyId,
    ts,
    nonce,
    signature,
    plainBytes: plain.length,
    requestBytes: Buffer.byteLength(body),
    items: parsed.items.length,
    audioBytes: audio ? audio.bytes : 0,
    videoBytes: video ? video.bytes : 0,
  };

  const bodyPath = path.join(outDir, `real-upload-body-${date}.json`);
  const headersPath = path.join(outDir, `real-upload-headers-${date}.json`);
  await fs.writeFile(bodyPath, body, "utf8");
  await fs.writeFile(headersPath, JSON.stringify(headers, null, 2), "utf8");
  console.log(JSON.stringify({ bodyPath, headersPath, ...headers }, null, 2));
}

main().catch((error) => {
  console.error(`MAKE_REAL_UPLOAD_BODY_FAILED: ${error.message}`);
  process.exit(1);
});
