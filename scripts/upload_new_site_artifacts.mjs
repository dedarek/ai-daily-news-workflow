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

function envFalse(value) {
  return ["0", "false", "no", "off"].includes(String(value || "").trim().toLowerCase());
}

function maxRequestBytes(args) {
  const raw = args["max-request-bytes"] || process.env.AI_DAILY_NEW_SITE_MAX_REQUEST_BYTES || "67108864";
  const parsed = Number.parseInt(raw, 10);
  if (!Number.isFinite(parsed) || parsed <= 0) {
    throw new Error(`Invalid max request bytes: ${raw}`);
  }
  return parsed;
}

function requireDate(date) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date || "")) {
    throw new Error("--date is required and must be YYYY-MM-DD");
  }
}

function firstExisting(candidates, label) {
  return fs
    .stat(candidates[0])
    .then(() => candidates[0])
    .catch(async () => {
      for (const candidate of candidates.slice(1)) {
        try {
          const stat = await fs.stat(candidate);
          if (stat.isFile()) return candidate;
        } catch {
          // Try the next known artifact name.
        }
      }
      throw new Error(`Missing ${label}: ${candidates.join(", ")}`);
    });
}

function hashApiId(apiKey) {
  return createHash("sha256").update(apiKey).digest("hex").slice(0, 16);
}

function deriveKey(apiKey, id) {
  return scryptSync(
    apiKey,
    createHash("sha256").update(`ai-daily:${id}`).digest(),
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

function buildKeys(apiKey) {
  const apiKeyId = hashApiId(apiKey);
  const material = deriveKey(apiKey, apiKeyId);
  return { apiKeyId, encKey: hkdf(material, "enc"), macKey: hkdf(material, "mac") };
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

function buildUploadEnvelope(payload, apiKey) {
  const plain = Buffer.from(JSON.stringify(payload), "utf8");
  if (plain.length > 45 * 1024 * 1024) {
    throw new Error(`payload too large: ${plain.length} bytes > 45MB`);
  }

  const { apiKeyId, encKey, macKey } = buildKeys(apiKey);
  const { iv, tag, ct } = encrypt(plain, encKey);
  const ts = Date.now().toString();
  const nonce = randomBytes(16).toString("hex");
  const signaturePayload = `${apiKeyId}|${ts}|${nonce}|${iv.toString("base64")}|${ct.toString("base64")}|${tag.toString("base64")}`;
  const signature = hmacSign(signaturePayload, macKey);
  const body = JSON.stringify({
    v: 1,
    apiKeyId,
    ts,
    nonce,
    iv: iv.toString("base64"),
    tag: tag.toString("base64"),
    ct: ct.toString("base64"),
  });
  return { apiKeyId, ts, nonce, signature, body, plainBytes: plain.length, requestBytes: Buffer.byteLength(body) };
}

function displayDate(date) {
  const [year, month, day] = date.split("-");
  return `${year}年${month}月${day}日`;
}

function weekday(date) {
  return ["周日", "周一", "周二", "周三", "周四", "周五", "周六"][new Date(`${date}T00:00:00+08:00`).getDay()];
}

const KNOWN_CATEGORY_LABELS = new Set([
  "焦点",
  "产品发布",
  "行业动态",
  "前沿研究",
  "开源热榜",
  "Agent & 工具",
  "Agent&工具",
  "商业融资",
]);

const CATEGORY_EMOJI = {
  "焦点": "🔥",
  "产品发布": "🚀",
  "行业动态": "💼",
  "前沿研究": "💡",
  "开源热榜": "🔓",
  "Agent & 工具": "🤖",
  "Agent&工具": "🤖",
  "商业融资": "💰",
};

function normalizeCategoryLabel(value) {
  const label = String(value || "").replace(/^[🔥🚀💼💡🔓🤖💰]\s*/u, "").trim();
  if (!label) return "焦点";
  return label === "今日焦点" ? "焦点" : label;
}

function categoryTextHeading(category) {
  const label = normalizeCategoryLabel(category);
  const emoji = CATEGORY_EMOJI[label] || "🔥";
  return `${emoji} ${label}`;
}

function categoryHeading(line) {
  const trimmed = line.trim();
  const emojiMatch = trimmed.match(/^([🔥🚀💼💡🔓🤖💰])\s*(.*)$/u);
  if (emojiMatch) {
    return normalizeCategoryLabel(emojiMatch[2] || "焦点");
  }
  return KNOWN_CATEGORY_LABELS.has(trimmed) ? normalizeCategoryLabel(trimmed) : null;
}

function categoryLabel(article) {
  return normalizeCategoryLabel(article.category || article.section || article.topic || "焦点");
}

function articleTitle(article) {
  return String(article.title || article.headline || "").trim();
}

function articleBody(article) {
  return String(article.body || article.summary || article.description || "").trim();
}

function articleReview(article) {
  return String(article.review || article.comment || article.editorial || article.ai_review || "").trim();
}

function articleUrl(article) {
  return String(article.url || article.link || article.source_url || "").trim();
}

function renderNewsText(date, articles, summary) {
  const lines = [];
  const intro = String(summary || "").trim();
  if (intro) {
    lines.push(intro);
    lines.push("");
  }
  let currentCategory = "";
  for (const article of articles) {
    const title = articleTitle(article);
    if (!title) continue;
    const category = categoryLabel(article);
    if (category !== currentCategory) {
      lines.push(categoryTextHeading(category));
      lines.push("");
      currentCategory = category;
    }
    lines.push(title);
    const body = articleBody(article);
    if (body) lines.push(body);
    const review = articleReview(article);
    if (review) lines.push(`AI锐评：${review}`);
    const url = articleUrl(article);
    if (url) lines.push(`🔗 ${url}`);
    lines.push("");
  }
  if (!currentCategory) {
    throw new Error(`No uploadable article text rendered for ${date}`);
  }
  return `${lines.join("\n").trim()}\n`;
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
    const heading = categoryHeading(line);
    if (heading) {
      flush();
      activeCategory = heading;
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

async function readJson(file) {
  return JSON.parse(await fs.readFile(file, "utf8"));
}

async function readMedia(file) {
  const data = await fs.readFile(file);
  const ext = path.extname(file).slice(1).toLowerCase();
  const mime = ["mp3", "wav", "m4a"].includes(ext)
    ? `audio/${ext === "mp3" ? "mpeg" : ext}`
    : ["mp4", "webm", "mov"].includes(ext)
      ? `video/${ext}`
      : "application/octet-stream";
  return { name: path.basename(file), mime, data: data.toString("base64"), bytes: data.length };
}

async function main() {
  const args = parseArgs();
  const date = args.date;
  requireDate(date);

  const endpoint = (args.endpoint || process.env.AI_DAILY_NEW_SITE_ENDPOINT || "http://47.108.192.42:4000/daily").replace(/\/$/, "");
  const apiKey = args["api-key"] || process.env.AI_DAILY_NEW_SITE_API_KEY;
  if (!apiKey) throw new Error("AI_DAILY_NEW_SITE_API_KEY is required");

  const distDir = path.resolve(args["artifact-dir"] || "dist");
  const articlesPath = args.articles || await firstExisting(
    [
      path.join(distDir, `articles-${date}.json`),
      path.join(distDir, `news-data-${date}.json`),
    ],
    "articles JSON",
  );
  const reportPath = args.report || await firstExisting(
    [path.join(distDir, `pipeline-report-${date}.json`)],
    "pipeline report",
  );
  const audioPath = args.audio || await firstExisting(
    [
      path.join(distDir, `daily-news-podcast-${date}.mp3`),
      path.join(distDir, `ai-daily-news-podcast-${date}.mp3`),
    ],
    "audio",
  );
  const videoPath = args.video || await firstExisting(
    [
      path.join(distDir, `daily-news-video-${date}.mp4`),
      path.join(distDir, `ai-daily-news-video-${date}.mp4`),
    ],
    "video",
  );
  const textPath = args.txt || path.join(distDir, `daily-news-text-${date}.txt`);

  const articles = await readJson(articlesPath);
  const report = await readJson(reportPath);
  if (!Array.isArray(articles)) throw new Error(`Articles JSON must be an array: ${articlesPath}`);
  const summary = report.digest_summary || report.summary || report.title || "";
  await fs.mkdir(path.dirname(textPath), { recursive: true });
  await fs.writeFile(textPath, renderNewsText(date, articles, summary), "utf8");

  const raw = await fs.readFile(textPath, "utf8");
  const parsed = parseNewsText(raw);
  const audio = await readMedia(audioPath);
  const uploadVideo = !envFalse(args["upload-video"] || process.env.AI_DAILY_NEW_SITE_UPLOAD_VIDEO || "true");
  const video = uploadVideo ? await readMedia(videoPath) : null;
  let payload = {
    date,
    title: args.title || `AI 晚报：${date} 行业要闻速览`,
    intro: parsed.intro,
    weekday: weekday(date),
    displayDate: displayDate(date),
    audio,
    video,
    items: parsed.items,
  };

  const requestLimit = maxRequestBytes(args);
  let envelope = buildUploadEnvelope(payload, apiKey);
  if (video && envelope.requestBytes > requestLimit) {
    console.warn(
      `UPLOAD_VIDEO_SKIPPED reason=request_too_large request_bytes=${envelope.requestBytes} limit=${requestLimit} video_bytes=${video.bytes}`,
    );
    payload = { ...payload, video: null };
    envelope = buildUploadEnvelope(payload, apiKey);
  }
  if (envelope.requestBytes > requestLimit) {
    throw new Error(`upload request too large: ${envelope.requestBytes} bytes > ${requestLimit} bytes`);
  }
  const uploadUrl = `${endpoint}/api/upload`;

  console.log(JSON.stringify({
    upload_url: uploadUrl,
    date,
    text: textPath,
    items: parsed.items.length,
    audio_bytes: audio.bytes,
    video_bytes: payload.video ? payload.video.bytes : 0,
    payload_bytes: envelope.plainBytes,
    request_bytes: envelope.requestBytes,
  }, null, 2));

  if (args["dry-run"] === "true") {
    console.log("DRY_RUN: upload skipped");
    return;
  }

  let response;
  try {
    response = await fetch(uploadUrl, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "x-api-key-id": envelope.apiKeyId,
        "x-timestamp": envelope.ts,
        "x-nonce": envelope.nonce,
        "x-signature": envelope.signature,
        "User-Agent": "ai-daily-news-workflow/1.0",
      },
      body: envelope.body,
    });
  } catch (error) {
    console.error(JSON.stringify({
      upload_url: uploadUrl,
      request_bytes: envelope.requestBytes,
      payload_bytes: envelope.plainBytes,
      error_name: error.name,
      error_message: error.message,
      cause_name: error.cause?.name,
      cause_code: error.cause?.code,
      cause_message: error.cause?.message,
    }, null, 2));
    throw error;
  }
  const text = await response.text();
  let body;
  try {
    body = JSON.parse(text);
  } catch {
    body = { raw: text };
  }
  console.log(JSON.stringify({ status: response.status, response: body }, null, 2));
  if (!response.ok) {
    throw new Error(`new site upload failed: HTTP ${response.status}`);
  }
}

main().catch((error) => {
  console.error(`UPLOAD_NEW_SITE_FAILED: ${error.message}`);
  process.exit(1);
});
