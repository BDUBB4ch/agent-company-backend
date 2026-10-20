# Email -> Instagram carousel (PAUSED by Barry 2026-10-18 13:40: "pause the instagram stuff for now")

Barry, 2026-10-18: "that last email vivian and derek did, i like it. the missing llink and x cell. i want them to make
instagram posts out of that. i may need them to do it every time. make an email and turn it into a post too"
He said YES to the plan below, then paused it before any code was written. Nothing built; this is the whole plan.

The email: approval #630 "Your feed isn't the problem. Uptake is." (Derek's sheet + Vivian's design, both in
data/email_designs/630/: sheet.json, design.json, prices.json, preview.png).

## What gets built (new module backend/instagram_post.py)
1. SLIDES (no model turn): Vivian's email design re-laid-out as a 4:5 carousel, 1080x1350 PNGs:
   hero (eyebrow / headline with the accent word in orange / subhead / real product photo), one slide per SECTION
   (heading + text, type auto-shrunk to fit), the POINTS as 01/02/03, PRODUCTS with the live "From $" prices
   (prices.json), the OFFER (BIG15 + "link in bio"). Brand = email_design.BRAND + FONT. Rendered by headless Firefox
   (email_design.FIREFOX, --window-size=1080,1350, no crop). Product photos: social_cadence.product_photo_for(name)
   (local data/product-images; both #630 products resolve), else download from the store URL in product_card().
2. WORDS (one Derek turn): Instagram caption from HIS sheet (hook line first, no links, "link in bio", 5-10 hashtags),
   factcheck.check_email on it, one re-run on problems. Crop-neutral like the email (it feeds the store).
3. VIVIAN'S LOOK (one turn, skipped if the card is busy, the row says so): she opens the contact sheet
   (look_at_render) and says what she would change -- her words attached, nothing rewritten.
4. DELIVERY: Desktop\Instagram Posts\<date> <subject>\slide-01..NN.png + contact-sheet.png + caption.txt +
   hashtags.txt + post-instagram.txt; a social_post row on his board with the contact sheet as its file; the slides
   registered on the DESK (agent_files.register_file, creative). He posts. No Meta API, nothing sent.
5. EVERY TIME: email_cadence line ~371, after design_with_vivian() returns True -> instagram_post.make_from_email(aid)
   when setting `email_to_instagram` is on (default on). Plus tool `email_to_instagram(draft_id)` for Derek and Vivian
   (llm_router dispatch like product_video; main.py seat lists; a persona line each -- a tool without a persona
   mention gets bluffed).
6. FIRST RUN: #630. Slides render on the CPU any time; Derek's and Vivian's turns wait for the card
   (data/video_rendering.flag) like every office turn.

Cost: two model turns per email. Open question for Barry: Instagram is his cannabis lane (social_cannabis_platforms),
but an email-derived post is crop-neutral by construction -- fine unless he wants a cannabis-forward variant.
