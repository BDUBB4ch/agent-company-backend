"""Make the 🎤 button usable for actually TALKING, not one short phrase.

Barry, 2026-08-29: "lets get this mic thing fixed first" -- he needs it for the
voice-DNA interview, where the whole point is rambling out loud for a minute.

What was broken (identical code in all five neo decks):
  1. `continuous` never set -> defaults FALSE, so recognition ENDS at his first
     pause. A long answer is cut off after one sentence.
  2. only `e.results[0][0]` was read -> even with continuous on, everything
     after the first phrase was thrown away.
  3. no `onerror` -> a blocked mic permission silently turned the button off
     with no explanation at all.
  4. no interim feedback -> no way to tell it was hearing anything.

The fix keeps the same one-button toggle and the same target input, so nothing
else about the decks changes. Applies to every deck that has the button
(his standing "fix all, all the time" rule); the classic dashboard has no mic
and is left alone.
"""
import os
import re

DASH = r"C:\Users\Owner\Desktop\AgentDashboard"
DECKS = ["neo-chamber.html", "neo.html", "neo-roll6.html", "neo-holo.html",
         "neo-v4.html"]

OLD_RE = re.compile(
    r'\$\("b-mic"\)\.onclick = \(\) => \{\n'
    r'  if \(!SR\) \{ toast\("No speech recognition in this browser\."\); return; \}\n'
    r'  if \(rec\) \{ rec\.stop\(\); return; \}\n'
    r'  rec = new SR\(\); rec\.lang = "en-US"; rec\.interimResults = false;\n'
    r'  \$\("b-mic"\)\.classList\.add\("on"\);\n'
    r'  rec\.onresult = \(e\) => \{ \$\("con-input"\)\.value \+= \(\(\$\("con-input"\)\.value \? " " : ""\) \+ e\.results\[0\]\[0\]\.transcript\); \};\n'
    r'  rec\.onend = \(\) => \{ \$\("b-mic"\)\.classList\.remove\("on"\); rec = null; \};\n'
    r'  rec\.start\(\);\n'
    r'\};')

NEW = '''$("b-mic").onclick = () => {
  if (!SR) { toast("No speech recognition in this browser."); return; }
  if (rec) { rec.stop(); return; }              // second click = stop
  rec = new SR();
  rec.lang = "en-US";
  // DICTATION, NOT ONE PHRASE (2026-08-29). continuous keeps it listening
  // through pauses so a long spoken answer survives; interimResults shows
  // words as they land so you can see it working.
  rec.continuous = true;
  rec.interimResults = true;
  const box = $("con-input");
  let settled = box.value;                      // text already typed
  $("b-mic").classList.add("on");
  rec.onresult = (e) => {
    // EVERY result, not just results[0] -- the old code kept the first
    // phrase and silently dropped the rest of the sentence.
    let live = "";
    for (let i = e.resultIndex; i < e.results.length; i++) {
      const chunk = e.results[i][0].transcript;
      if (e.results[i].isFinal) settled += (settled ? " " : "") + chunk.trim();
      else live += chunk;
    }
    box.value = settled + (live ? (settled ? " " : "") + live : "");
    box.scrollTop = box.scrollHeight;
  };
  rec.onerror = (e) => {
    // Silent failure was the worst part: a blocked mic just turned the
    // button off and looked like nothing happened.
    const why = e.error === "not-allowed"
      ? "Microphone blocked — allow it in the address-bar icon, then try again."
      : e.error === "no-speech" ? "Didn't hear anything."
      : e.error === "audio-capture" ? "No microphone found."
      : "Mic error: " + e.error;
    toast(why);
  };
  rec.onend = () => {
    $("b-mic").classList.remove("on");
    box.value = settled;                        // drop any dangling interim
    rec = null;
  };
  rec.start();
  toast("Listening — click the mic again when you're done.");
};'''


def main():
    for name in DECKS:
        p = os.path.join(DASH, name)
        s = open(p, encoding="utf-8").read()
        if "DICTATION, NOT ONE PHRASE" in s:
            print(f"{name}: already fixed")
            continue
        new, n = OLD_RE.subn(lambda m: NEW, s, count=1)
        if n != 1:
            print(f"{name}: ANCHOR NOT FOUND ({n} matches) -- skipped")
            continue
        tmp = p + ".tmp"
        open(tmp, "w", encoding="utf-8").write(new)
        os.replace(tmp, p)
        back = open(p, encoding="utf-8").read()
        assert "rec.continuous = true" in back and "onerror" in back
        assert "e.results[0][0]" not in back.split("b-mic")[1][:2000]
        print(f"{name}: mic fixed ({len(s):,} -> {len(back):,})")


if __name__ == "__main__":
    main()
