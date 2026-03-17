---
name: email-rewrite
description: Rewrite and polish email content for better expression, clarity, and tone. Paste your draft email and get an improved version back. Activates on requests like "rewrite this email", "improve my email", "polish this message", "make this email better", or "help me with this email".
---

# Email Rewrite Skill

Use this skill when the user pastes an email draft and wants it improved, e.g.:
- "Rewrite this email"
- "Polish this message"
- "Improve my email"
- "Make this sound better"
- "Help me with this email"
- "Fix my email"

## Defaults

| Parameter | Default |
|---|---|
| Language | English |
| Tone | Auto-detect from the original draft |
| Output | Rewritten email only |
| Length | Keep similar length to original; trim filler but don't cut substance |

User overrides these defaults at any time (e.g., "make it more formal", "keep it short").

## Core Rewriting Principles

### 1. Expression & Clarity
- Replace vague or wordy phrases with precise, natural alternatives
- Eliminate redundancy, filler words, and unnecessary hedging
- Use active voice where it sounds more natural
- Ensure each sentence carries clear meaning

### 2. Tone Matching
- **Auto-detect** the original tone (formal, friendly-professional, casual, urgent, apologetic, etc.)
- Preserve the sender's intent and personality — don't make it sound robotic
- If the tone is unclear, default to **friendly professional**
- Adjust formality only when the user explicitly asks

### 3. Structure & Flow
- Use short paragraphs (2–4 sentences max)
- Lead with the main point or ask — don't bury it
- Use logical transitions between ideas
- End with a clear call-to-action or closing when appropriate

### 4. Common Fixes
- Fix grammar, spelling, and punctuation errors
- Correct awkward phrasing or non-native patterns
- Replace overused email clichés with fresher alternatives:
  - ❌ "I hope this email finds you well" → ✅ (omit or use a context-appropriate opener)
  - ❌ "Please do not hesitate to contact me" → ✅ "Feel free to reach out"
  - ❌ "As per our previous discussion" → ✅ "As we discussed"
  - ❌ "I am writing to inform you that" → ✅ (just state the information)
  - ❌ "Kindly revert back" → ✅ "Please let me know"

### 5. What NOT to Change
- Do not alter factual content, names, dates, numbers, or specific details
- Do not add information that wasn't in the original
- Do not change the sender's core message or stance
- Do not remove important context the sender included for a reason

## Workflow

1. **Receive** the user's draft email (pasted text)
2. **Analyze** the tone, intent, audience, and structure
3. **Rewrite** applying the principles above
4. **Output** the polished email only — clean and ready to copy-paste

## Output Format

Return the rewritten email as plain text, formatted exactly as it should appear when sent. Do not wrap it in code blocks or add commentary unless the user asks for explanations.

If the email has a subject line, improve it too and place it at the top:

```
Subject: [improved subject line]

[improved email body]
```

## Handling Edge Cases

- **Very short emails** (1–2 sentences): Focus on word choice and clarity; don't over-expand
- **Very long emails**: Tighten aggressively; suggest splitting into multiple emails if appropriate
- **Emotional/sensitive emails**: Preserve the emotion but smooth rough edges; ask before softening strong language
- **Technical emails**: Keep jargon that the audience would understand; clarify only non-obvious terms
- **Reply chains**: Only rewrite the user's new reply, not quoted previous messages

## User Overrides

The user can customize behavior at any time:
- "Make it more formal" / "Make it casual"
- "Keep it under 3 sentences"
- "Add a subject line"
- "Make it more direct"
- "Soften the tone"
- "Make it more persuasive"
