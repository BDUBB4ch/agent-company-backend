"""Derek redrafts this week's email after Barry turned down #541 ("we did the coco already"), 2026-10-02.
Same path as the scheduled job (email_cadence.draft: Derek writes -> Vivian designs -> render -> Pending Review), now
with the last 8 weeks of subjects in front of him. Verifies a new designed card exists and is not about coco."""
import asyncio
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))
os.chdir(os.path.join(ROOT, "backend"))
import email_cadence  # noqa: E402
import memory  # noqa: E402


async def main() -> None:
    slots = email_cadence.upcoming_slots()
    send_at, idx = slots[0]
    kind = email_cadence.kind_for(send_at, idx)
    print(f"redrafting {kind} for {send_at}", flush=True)
    res = await email_cadence.draft(kind, send_at)
    print("result:", {k: v for k, v in res.items() if k in ("ok", "approval_id", "why")}, flush=True)
    aid = res.get("approval_id")
    if aid:
        with memory.get_db() as conn:
            row = conn.execute("SELECT content, file_path FROM approvals WHERE id = ?", (aid,)).fetchone()
        subject = (row[0] or "").strip().splitlines()[0]
        print(f"card #{aid}: '{subject}' | preview: {row[1]} exists={os.path.isfile(row[1] or '')}", flush=True)
        print("COCO REPEAT" if "coco" in subject.lower() else "new topic", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
