// ╭─────────────────────────────────────────────────────── ♱ · 𓆩🤍𓆪 · ♱ ─╮
//      SECTION: wispimages, the Cloudflare Worker that makes Wisp's pictures
// ╰─ ♱ · 𓆩🤍𓆪 · ♱ ───────────────────────────────────────────────────────╯
//
// Deployed by hand in the Cloudflare dashboard (Myra's account,
// Workers & Pages, "wispimages"). It needs a Workers AI binding named AI
// (Settings, Bindings, Add, Workers AI, variable name AI).
//
// Two ways to ask, both at <CF_IMAGE_WORKER_URL from .env>:
//
//   Words only (FLUX.1 schnell):
//     GET  ?prompt=...   or POST JSON {"prompt": "..."}
//
//   Words and a reference picture (FLUX.2 klein 4B):
//     POST multipart/form-data with the fields
//       prompt     the words
//       reference  a PNG or JPEG under 512 x 512 that the model copies the
//                  character from (Wisp's art for his life stage)
//
// Answer: the picture (image/png or image/jpeg, whichever the model made),
// or a plain-text reason with 400 or 502.

const WORDS_MODEL = "@cf/black-forest-labs/flux-1-schnell";
const REFERENCE_MODEL = "@cf/black-forest-labs/flux-2-klein-4b";
const SIDE = "1024";

// ╭─────────────────────────────────────────────────────── ♱ · 𓆩🤍𓆪 · ♱ ─╮
//      SECTION: reading the request into a prompt and a reference
// ╰─ ♱ · 𓆩🤍𓆪 · ♱ ───────────────────────────────────────────────────────╯

class BadRequest extends Error {}

async function readAsk(request) {
  const url = new URL(request.url);
  const type = request.headers.get("content-type") ?? "";
  if (request.method === "POST" && type.startsWith("multipart/form-data")) {
    const form = await request.formData();
    const reference = form.get("reference");
    if (reference !== null && typeof reference === "string") {
      throw new BadRequest("reference must be a picture file, not text");
    }
    return { prompt: form.get("prompt"), reference };
  }
  if (request.method === "POST") {
    try {
      const body = await request.json();
      return { prompt: body.prompt ?? url.searchParams.get("prompt"), reference: null };
    } catch {
      throw new BadRequest('Body must be JSON {"prompt": "..."} or multipart form data');
    }
  }
  return { prompt: url.searchParams.get("prompt"), reference: null };
}

// ╭─────────────────────────────────────────────────────── ♱ · 𓆩🤍𓆪 · ♱ ─╮
//      SECTION: asking the two models
// ╰─ ♱ · 𓆩🤍𓆪 · ♱ ───────────────────────────────────────────────────────╯

async function drawFromWords(env, prompt) {
  const result = await env.AI.run(WORDS_MODEL, { prompt, steps: 4 });
  return result.image;
}

async function drawFromReference(env, prompt, reference) {
  const form = new FormData();
  form.append("prompt", prompt);
  form.append("width", SIDE);
  form.append("height", SIDE);
  form.append("input_image_0", reference);
  // FormData hides its boundary; a Response serializes it and sets the
  // multipart content type with the boundary the model needs.
  const serialized = new Response(form);
  const result = await env.AI.run(REFERENCE_MODEL, {
    multipart: {
      body: serialized.body,
      contentType: serialized.headers.get("content-type"),
    },
  });
  return result.image;
}

function pictureResponse(base64) {
  const bytes = Uint8Array.from(atob(base64), (c) => c.charCodeAt(0));
  const isPng = bytes[0] === 0x89 && bytes[1] === 0x50 && bytes[2] === 0x4e;
  return new Response(bytes, {
    headers: { "Content-Type": isPng ? "image/png" : "image/jpeg" },
  });
}

// ╭─────────────────────────────────────────────────────── ♱ · 𓆩🤍𓆪 · ♱ ─╮
//      SECTION: the worker
// ╰─ ♱ · 𓆩🤍𓆪 · ♱ ───────────────────────────────────────────────────────╯

export default {
  async fetch(request, env) {
    let ask;
    try {
      ask = await readAsk(request);
    } catch (error) {
      if (error instanceof BadRequest) {
        return new Response(error.message, { status: 400 });
      }
      return new Response("Could not read the request: " + error.message, { status: 400 });
    }
    if (!ask.prompt) {
      return new Response("Missing prompt", { status: 400 });
    }
    try {
      const base64 = ask.reference
        ? await drawFromReference(env, ask.prompt, ask.reference)
        : await drawFromWords(env, ask.prompt);
      if (!base64) {
        return new Response("Image generation failed: the model sent no picture", { status: 502 });
      }
      return pictureResponse(base64);
    } catch (error) {
      return new Response("Image generation failed: " + error.message, { status: 502 });
    }
  },
};
