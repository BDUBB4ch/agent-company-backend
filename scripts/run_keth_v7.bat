@echo off
REM Keth v7: complete redo, Barry's call 2026-08-08 ("complete redo. Start V7").
REM Same confirmed source set as v6 (lora_keth_v5 -- 65 frames built from the 17
REM files Barry confirmed, pre-flight clean, 0.3%% white padding), trained from
REM scratch rather than continued.
REM
REM NOTE FOR WHOEVER READS THIS LATER: the character canon does NOT enter
REM training. Every caption in this set is deliberately minimal (@Keth, close-up
REM portrait / full body / plain background) because captions carrying the full
REM spec was bug 3 in the 2026-08-08 post-mortem -- the model explains the image
REM with ordinary words and the @Keth trigger learns nothing. Canon governs
REM PROMPTING and frame selection, never caption text.
cd /d "%~dp0.."
call scripts\train_one_v4.bat keth lora_keth_v5 v7 <nul > data\train_keth_v7.log 2>&1
