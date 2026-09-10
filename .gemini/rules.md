# Antigravity Rules — Vision-Based Autonomous Robotic Arm Project

## ⚠️ PRIME DIRECTIVE (THE MOST IMPORTANT RULE OF THE ENTIRE PROJECT)

**EVERY SINGLE MOVEMENT of the 6-DOF robotic arm — no matter when, where, or how it is triggered (PS5 teleoperation joysticks, web sliders, automated routines, Home, Lock 90°, Cartesian IK mode, or autonomous inference) — MUST ALWAYS BE EXTREMELY SMOOTH WITH ZERO SUDDEN MOVEMENTS, ZERO JERK, AND ZERO CURRENT SPIKES.**

---

## MANDATORY: Context Loading

**Before responding to ANY user request, you MUST:**

1. Read `/Users/sohambhavsar/Desktop/Autonomoous arm/agent_bible.md` — this contains all project context, locked decisions, current status, and conversation history.
2. Read `/Users/sohambhavsar/Desktop/Autonomoous arm/architecture.md` — this contains the full system architecture.
3. Read `/Users/sohambhavsar/Desktop/Autonomoous arm/decisions.md` — this contains the chronological decision log with full rationale.

**Do NOT skip this step.** Do NOT rely on memory. Do NOT guess what was decided previously. READ THE FILES.

## Project Behavior Rules

1. **Never jump ahead.** The user builds incrementally. Always validate the current step is complete before suggesting the next one.
2. **Never agree blindly.** Act as a senior robotics engineer. Critically evaluate every design decision. Point out flaws. Suggest better alternatives with trade-off analysis.
3. **Update `agent_bible.md` after every session.** Add new decisions, update project status, append session summary.
4. **Update `decisions.md` after every new decision.** Append-only. Never delete or modify past entries.
5. **Heavy code comments.** Every file must have a header explaining WHY it exists and WHERE it fits in the system. Reference decision numbers from `agent_bible.md` where relevant.
6. **Git discipline.** After completing a logical unit of work or significant file update, automatically commit the changes and push directly to GitHub (`git push origin main`).
7. **No hallucinated libraries.** Before using any Python or Arduino library, verify it exists and is correct. Prefer well-known, well-documented libraries.
8. **Respect locked decisions.** Decisions in `agent_bible.md` Section 3 are FINAL. Do not re-question them unless the user explicitly asks to revisit.

## Tech Stack (Locked)

- Arduino Firmware: C++ with Wire.h + Adafruit_PWMServoDriver
- Python Backend: FastAPI + WebSockets + pyserial + opencv-python
- Frontend: Vanilla HTML + CSS + JavaScript (NO React, NO Vue, NO Tailwind)
- Dashboard Theme: Warm light mode (cream/linen/sand). See agent_bible.md Decision #18.
- Arduino Management: Arduino CLI (until Raspberry Pi migration)
- Fonts: DM Serif Display, Source Sans 3, IBM Plex Mono
