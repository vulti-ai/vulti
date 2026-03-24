---
name: fal-ai
description: Generate images using FAL.ai (FLUX models). Covers model selection, prompting, sizing, and cost-aware generation.
version: 1.0.0
author: Vulti
license: MIT
triggers:
  - "generate image"
  - "create image"
  - "make me a picture"
  - "draw"
  - "image of"
  - "photo of"
  - "illustration of"
connection: fal-ai
metadata:
  vulti:
    tags: [image, generation, fal, flux, media]
    category: media
    related_skills: [ascii-art, excalidraw]
prerequisites:
  env: [FAL_KEY]
---

# FAL.ai Image Generation

You have a `generate_image` tool. Use it.

## Quick start

```
generate_image(prompt="a mountain landscape at sunset", image_size="landscape_4_3")
```

That's it. The tool handles auth, model selection, and file saving.

## Model selection

The tool uses FLUX 2 Pro by default. Override with `model`:

| Model | Speed | Quality | Cost | When to use |
|-------|-------|---------|------|-------------|
| `fal-ai/flux-2-pro` | Slow (~30s) | Best | $$$ | Final output, client-facing, high detail |
| `fal-ai/flux/schnell` | Fast (~2s) | Good | $ | Drafts, iterations, avatars, quick previews |
| `fal-ai/flux-2-pro/kontext` | Medium | Best + edit | $$ | Editing existing images, style transfer |

**Default to `fal-ai/flux/schnell` unless the user explicitly asks for high quality.** Don't burn money on drafts.

## Parameters

| Param | Default | Options |
|-------|---------|---------|
| `prompt` | required | Describe what you want. Be specific. |
| `image_size` | `landscape_4_3` | `square`, `square_hd`, `portrait_4_3`, `portrait_16_9`, `landscape_4_3`, `landscape_16_9` |
| `num_images` | 1 | 1-4 |
| `output_format` | `png` | `png`, `jpeg` |
| `num_inference_steps` | 50 | 1-100 (use 4 for schnell, 20-30 for pro) |
| `guidance_scale` | 4.5 | 0.1-20 |

## Prompting tips

Good prompts are specific about:
- **Subject**: what is in the image
- **Style**: "digital art", "photograph", "watercolor", "minimalist icon", "3D render"
- **Composition**: "close-up", "wide angle", "top-down view", "centered"
- **Mood/lighting**: "warm sunset light", "dramatic shadows", "soft diffused"
- **Background**: "white background", "gradient", "urban street"

Bad: "a cat"
Good: "a tabby cat sitting on a windowsill, golden hour sunlight, soft focus background, warm tones, photography style"

## Upscaling

The tool can auto-upscale images using `fal-ai/clarity-upscaler`. Set `upscale=true` in the tool call if available, or generate at `square_hd` for higher base resolution.

## File output

Generated images are saved to the agent's cache directory: `~/.vulti/agents/{id}/cache/`

The tool returns the file path. You can reference it in messages or send it via Matrix.

## Cost awareness

- schnell: ~$0.003/image — use for everything except final output
- pro: ~$0.05/image — only when quality matters
- Always generate 1 image first. Only generate multiple if the user asks.
- Don't upscale unless asked.
