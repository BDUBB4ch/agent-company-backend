r"""One-off patch (2026-10-08 11:30): the fact net's send-back hands her THE RECORDS for each flagged part (the two
captured source texts that share the most words with the part), so she rewrites next to the facts instead of
re-inventing. Calibration (data/bench + the witch-garden draft): her narrative embellishes nearly every sentence
("Roman soldiers drank it from their canteens", "measuring the strength by how the skin felt") -- 92 of 97 flagged,
and two "fix or cut" rounds changed nothing. The office never writes her lines; it shows her the sources."""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def patch(path, pairs):
    t = open(path, encoding="utf-8").read()
    for a, b in pairs:
        assert t.count(a) == 1, (os.path.basename(path), a[:60])
        t = t.replace(a, b)
    open(path, "w", encoding="utf-8").write(t)
    print("ok", os.path.basename(path))


patch(os.path.join(ROOT, "backend", "video_queue.py"), [
(r'''        parts_hit = sorted({f["part"] for f in res["flags"]})
        listing = "\n".join(f"{n}. {video['parts'][n - 1].get('say', '')}" for n in parts_hit)
        msg = (fact_net.send_back_text(res["flags"])
               + f'\n\nAnswer as JSON only: {{"parts": [{{"n": N, "say": "..."}}]}} for parts {", ".join(map(str, parts_hit))}.'
               f"\n\nTHE PARTS AS THEY ARE:\n{listing}")''',
r'''        parts_hit = sorted({f["part"] for f in res["flags"]})
        listing = "\n".join(f"{n}. {video['parts'][n - 1].get('say', '')}" for n in parts_hit)
        # THE RECORDS, next to each flagged part: the two captured sources that share the most words with it
        stop = set("the a an and or of to in on for with by as is are was were be it its this that from at not".split())

        def words(s):
            return {w for w in re.findall(r"[a-z][a-z\-]{2,}", s.lower()) if w not in stop}
        src_words = [words(s) for s in sources]
        records = []
        for n in parts_hit:
            pw = words(str(video["parts"][n - 1].get("say", "")))
            best = sorted(range(len(sources)), key=lambda i: -len(pw & src_words[i]))[:2]
            picked = "\n".join("  " + " ".join(sources[i].split())[:1500] for i in best if pw & src_words[i])
            records.append(f"part {n}:\n{picked or '  (nothing you read matches this part)'}")
        msg = (fact_net.send_back_text(res["flags"])
               + "\n\nWHAT YOU ACTUALLY READ, for each part (write from THIS -- in your voice, but only what it "
                 "says; a legend or a claim you cannot find here is said as a legend, or cut):\n" + "\n".join(records)
               + f'\n\nAnswer as JSON only: {{"parts": [{{"n": N, "say": "..."}}]}} for parts {", ".join(map(str, parts_hit))}.'
               f"\n\nTHE PARTS AS THEY ARE:\n{listing}")'''),
])
