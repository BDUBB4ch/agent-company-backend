"""Append typed word-forms to the USE WHEN lines of the creative docs
(2026-09-10). Recall does no stemming and drops tokens under 3 chars, so a
routing line has to carry the words Barry actually types. Idempotent.
"""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FOLDER = os.path.join(ROOT, "knowledge", "creative")

EXTRA = {
    "product-photography-for-ecommerce.md":
        "take a picture of, need a picture of, need photos, need pictures, "
        "photos for the site, images for the listing, shoot it, staging, styled shot, "
        "on white, plain background, studio shot, macro, close up, closeup, "
        "detail shot, packshot, pack shot, catalogue photo, real photo, actual photo",
    "composition-and-visual-storytelling.md":
        "too tight, too wide, zoom out, zoom in, off center, off centre, centered, "
        "centred, symmetry, spacing, breathing room, empty space, whats in frame, "
        "in frame, out of frame, cut off, cropped weird, order of the images, "
        "which image first, gallery order, storytelling, tells a story",
    "colour-theory-and-brand-palette.md":
        "wrong green, wrong orange, off color, off colour, muddy, dull, "
        "clashing, clash, pop of color, pop of colour, brand palette, "
        "our colors, our colours, color rules, colour rules, swatch, swatches, "
        "cmyk, rgb, srgb, wcag, accessible color, accessible colour",
    "typography-logo-and-brand-identity.md":
        "type, typography, headline font, body font, font size, font sizes, "
        "readable text, text size, letter spacing, all caps, brand mark, monogram, "
        "icon, app icon, watermark, name change, new name, brand name, "
        "identity, look and feel, brand look, consistent branding, packaging text",
    "ai-image-generation-on-this-stack.md":
        "make an image, make a picture, make me an image, create an image, "
        "generate an image, generate a picture, image of, picture of, "
        "another version, try again, different version, seed, steps, "
        "why does it look, why do they look, hands are wrong, face is wrong, "
        "how long does a render take, how long will it take, render time, "
        "inpaint, edit that image, change that image, upscale",
    "social-and-ad-creative-design.md":
        "post, posts, posting, for instagram, for facebook, for tiktok, "
        "for youtube, for pinterest, for the socials, socials, feed post, "
        "ad for, ads for, creative for, cover image, cover photo, "
        "first frame, hook frame, text on the post, caption image, "
        "what dimensions, how big should, aspect for",
    "website-and-store-visual-design.md":
        "our site, the store looks, storefront, above the fold, "
        "nobody is buying, no orders, no sales, cart, checkout looks, "
        "product images on the site, thumbnails on the site, "
        "load slow, loading slow, too slow, big images, compress, "
        "phone view, mobile view, desktop view, layout of the page, page layout",
    "packaging-labels-print-and-signage.md":
        "bottle labels, our label, private label, white label, "
        "print it, get it printed, print shop, printer file, "
        "shipping boxes, mailer, mailers, tape, packing, "
        "shop sign, store sign, window sign, vinyl, banner stand, "
        "shirt, shirts, hat, hats, swag, giveaway",
    "marketing-video-and-motion-design.md":
        "make a video, make me a video, short video, quick video, "
        "product clip, show it moving, moving image, gif, "
        "footage, film, filming, record, recording, "
        "sound, audio, music, song, voice over, "
        "how long is the clip, seconds, vertical video, video size",
    "gotcho-back-fashion-and-product-visuals.md":
        "the bag brand, my bag brand, the other brand, other business, "
        "hemp, hemp bags, backpack photos, bag shots, model, models, "
        "wearing it, on a person, worn, lifestyle for the bags, "
        "brand for the bags, look for the bags, style for the bags, "
        "new bags, next drop, back in stock bags",
    "visual-qa-retouching-and-consistency.md":
        "is it good, is this good, good enough, ready to post, ready to use, "
        "something looks off, something is wrong, weird, strange, "
        "wrong color, wrong colour, wrong label, wrong bottle, "
        "doesnt match, does not match, not consistent, all look different, "
        "make them match, same style, edit it, crop it, resize, export",
    "how-vivian-works-creative-director-method.md":
        "where do we start, whats first, what do you need, what should we do, "
        "your method, how you work, how do you do it, take it from here, "
        "run with it, own this, plan for the visuals, visual plan, "
        "this week, weekly, what are you working on, whats on your plate",
}

for fn, extra in EXTRA.items():
    path = os.path.join(FOLDER, fn)
    if not os.path.isfile(path):
        print(f"  skip {fn} (not on disk)")
        continue
    lines = open(path, encoding="utf-8").read().split("\n")
    assert lines[0].startswith("USE WHEN:"), fn
    have = {t.strip().lower() for t in lines[0][len("USE WHEN:"):].split(",")}
    add = [t.strip() for t in extra.split(",") if t.strip().lower() not in have]
    if not add:
        print(f"  {fn}: nothing to add")
        continue
    lines[0] = lines[0].rstrip().rstrip(",") + ", " + ", ".join(add)
    assert len(lines[0]) < 1600, f"{fn}: routing line {len(lines[0])} chars"
    tmp = path + ".tmp"
    open(tmp, "w", encoding="utf-8", newline="").write("\n".join(lines))
    os.replace(tmp, path)
    print(f"  {fn}: +{len(add)} tokens (line now {len(lines[0])} chars)")
