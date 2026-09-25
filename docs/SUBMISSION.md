# Round 1 Submission Kit: StudyPilot

## 1. Project description

### One-liner (for "tagline" / short fields)
StudyPilot turns any college syllabus into an adaptive, day-by-day exam plan. Gemini reads the syllabus and quizzes you, a spaced-repetition scheduler builds the timetable, and the plan re-balances itself around what you've actually mastered or missed.

### Full description (~250 words)
**Problem.** Before exams, students juggle 40+ topics across several subjects with exams packed into a couple of weeks. They don't know how long each topic will take, they forget what they studied early on, and one missed day wrecks a static timetable. Generic planners know nothing about their syllabus or their understanding.

**Solution.** StudyPilot is an AI study planner. A student pastes their syllabus (or uploads the PDF) and sets their exam dates and daily study hours. Google Gemini extracts the subjects and splits units into study-sized topics, estimating difficulty and effort for each. A deterministic scheduler then builds a day-by-day plan. It interleaves subjects by urgency, adds spaced-repetition reviews at +1/+3/+7 days, puts a final revision block before every exam, and respects rest days. If the syllabus doesn't fit, it warns the student instead of silently dropping topics.

**Personalisation.** Every task has an AI tutor ("Explain", with follow-up questions) and an adaptive quiz pitched at the student's current mastery. Quiz scores update per-topic mastery. **Replan** rebuilds the rest of the calendar: weak topics get extra reviews, mastered ones are skipped, and missed tasks are redistributed. A Gemini "study coach" gives a focused nudge each day.

**Design choices.** We use a hybrid architecture: the LLM handles understanding and content, and a tested algorithm handles the calendar, so plans are always valid. The backend is stateless and progress stays in the browser (private, no login). The app degrades gracefully to offline heuristics if the AI is unavailable.

**Tech.** FastAPI, React (Vite), Google Gemini (JSON mode), Docker, Render. 21 automated tests, CI on GitHub Actions.

### Tags / categories
Education · Productivity · Student life · Generative AI

---

## 2. Demo video script (target 2:30)

Record at 1280×720 or 1920×1080 with the **live Render URL and a Gemini key set** (badge shows "Gemini AI"). Wake the Render instance a minute before you start. Use a clean browser profile or click **Reset** first. OBS or the Windows Game Bar (Win+G) both work, and Loom is fine too.

| Time | Screen | Say (roughly) |
|---|---|---|
| 0:00–0:15 | Landing page | "Every exam season, students get a syllabus with 40-plus topics and two weeks of exams. Most of us either don't plan, or we plan once and it breaks the first day we fall behind. This is StudyPilot." |
| 0:15–0:40 | Click **Try a sample syllabus** (or paste your real IIITM syllabus), then **Extract topics** | "I paste my syllabus exactly as it is. Gemini splits the units into study-sized topics and estimates how hard each one is and how many hours it needs. It also picks up the exam dates. I can edit anything." |
| 0:40–0:55 | Scroll to **Your routine**, set hours/day and rest days, then **Generate** | "I tell it I can study four and a half hours a day and I rest on Sundays. It checks whether the syllabus even fits before my last exam." |
| 0:55–1:20 | Dashboard: point at the day strip, click 2–3 future days, point at the Learn / Review / Revision pills | "This isn't an LLM guessing a timetable. A scheduler interleaves subjects by urgency, adds spaced-repetition reviews one, three and seven days after I learn something, and reserves a full revision block before each exam." |
| 1:20–1:45 | Tick a task, click **Explain**, ask a follow-up question | "Each task has an AI tutor pitched at my level. I can ask follow-up questions right here." |
| 1:45–2:10 | **Quiz me** on a topic, answer (get some wrong), **Check answers**, then **Update my plan**. Point at "Weak: …" | "Then it quizzes me. I got this one wrong, so the topic is marked weak, and when I update the plan it gets extra reviews. If I already know a topic, it gets skipped." |
| 2:10–2:30 | **Demo: time travel** → Day → twice → banner → **Replan** | "And real life: I skipped two days. Instead of the plan breaking, one click redistributes everything I missed across the days left before my exams. StudyPilot is a study plan that adapts to you. Thanks!" |

A 68-second silent screen recording of this exact flow is included as `studypilot_walkthrough.mp4`. It was recorded in offline mode, so it shows the offline badge and self-check quizzes. Use it as a reference or backup; the real AI-mode recording will be more impressive.

---

## 3. Submission checklist

- [ ] Create a GitHub repo `studypilot` (public) and push this folder (commands below)
- [ ] Get a Gemini key from https://aistudio.google.com/apikey
- [ ] Deploy on Render with **New + → Blueprint → select repo**, then paste `GEMINI_API_KEY` → wait for the build (~5 min)
- [ ] Open the live URL: the badge should say **Gemini AI**. Try the sample syllabus end to end
- [ ] Paste the live URL and video link into `README.md` (top) and push
- [ ] Record the 2–3 min demo (script above) and upload it to YouTube (unlisted) or Google Drive (anyone with link)
- [ ] Submit: description (section 1), video link, GitHub link, live link
- [ ] **If shortlisted, confirm participation immediately.** Only the first 30 confirmations get into Round 2

### Push to GitHub
```bash
cd studypilot
git remote add origin https://github.com/<your-username>/studypilot.git
git branch -M main
git push -u origin main
```
