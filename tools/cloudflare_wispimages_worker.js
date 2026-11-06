// ╭─────────────────────────────────────────────────────── ♱ · 𓆩🤍𓆪 · ♱ ─╮
//      SECTION: wispimages, the Cloudflare Worker that makes Wisp's pictures
// ╰─ ♱ · 𓆩🤍𓆪 · ♱ ───────────────────────────────────────────────────────╯
//
// Deployed by hand in the Cloudflare dashboard (Myra's account,
// Workers & Pages, "wispimages"). It needs a Workers AI binding named AI
// (Settings, Bindings, Add, Workers AI, variable name AI).
//
// Ask: GET  <CF_IMAGE_WORKER_URL from .env>?prompt=...
//   or POST the same URL with JSON {"prompt": "..."}
// Answer: the picture as image/jpeg, or a plain-text reason with 400 or 502.

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    let prompt = url.searchParams.get("prompt");
    if (request.method === "POST") {
      try {
        const body = await request.json();
        prompt = body.prompt ?? prompt;
      } catch {
        return new Response('Body must be JSON: {"prompt": "..."}', { status: 400 });
      }
    }
    if (!prompt) {
      return new Response("Missing prompt", { status: 400 });
    }
    try {
      const result = await env.AI.run("@cf/black-forest-labs/flux-1-schnell", {
        prompt,
        steps: 4,
      });
      const bytes = Uint8Array.from(atob(result.image), (c) => c.charCodeAt(0));
      return new Response(bytes, { headers: { "Content-Type": "image/jpeg" } });
    } catch (error) {
      return new Response("Image generation failed: " + error.message, { status: 502 });
    }
  },
};
