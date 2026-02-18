import os
import base64
import json
from urllib.parse import urlparse
from flask import Flask, render_template, request, jsonify, url_for
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Ensure template/static changes appear immediately during local development.
app.config["TEMPLATES_AUTO_RELOAD"] = True
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0

SUBJECT_SYSTEM_PROMPTS = {
    "math": (
        "You are Harold, a math-only tutor. "
        "Only answer questions related to math (arithmetic, algebra, geometry, trigonometry, calculus, statistics, word problems). "
        "If the user asks anything not related to math, refuse briefly and ask for a math question."
    ),
    "science": (
        "You are Harold, a science-only tutor. "
        "Only answer science questions (biology, chemistry, physics, earth science). "
        "If the user asks anything not related to science, refuse briefly and ask for a science question."
    ),
    "history": (
        "You are Harold, a history-only tutor. "
        "Only answer history questions (historical events, eras, people, timelines, causes/effects). "
        "If the user asks anything not related to history, refuse briefly and ask for a history question."
    ),
    "english": (
        "You are Harold, an English-only tutor. "
        "Only answer English class questions (grammar, writing, reading comprehension, vocabulary, literature analysis). "
        "If the user asks anything not related to English class, refuse briefly and ask for an English question."
    ),
}

# In-memory flow state keyed by client IP for image-based step verification.
image_sessions = {}

# In-memory chat history keyed by client IP and subject.
chat_sessions = {}
MAX_HISTORY_MESSAGES = 12

MATH_KEYWORDS = {
    "math", "algebra", "geometry", "trigonometry", "trig", "calculus", "derivative",
    "integral", "equation", "solve", "simplify", "factor", "fraction", "decimal",
    "percent", "probability", "statistics", "mean", "median", "mode", "sum",
    "difference", "product", "quotient", "slope", "angle", "area", "volume",
    "perimeter", "ratio", "proportion", "polynomial", "integer", "variable"
}

SCIENCE_KEYWORDS = {
    "science", "biology", "chemistry", "physics", "earth", "cell", "atom", "molecule",
    "energy", "force", "motion", "gravity", "photosynthesis", "ecosystem", "organism",
    "matter", "reaction", "periodic", "experiment", "hypothesis", "lab", "planet"
}

HISTORY_KEYWORDS = {
    "history", "historical", "ancient", "medieval", "empire", "revolution", "war",
    "civilization", "timeline", "era", "century", "dynasty", "treaty", "president",
    "king", "queen", "world war", "industrial", "colony", "constitution"
}

ENGLISH_KEYWORDS = {
    "english", "grammar", "essay", "paragraph", "sentence", "verb", "noun", "adjective",
    "adverb", "punctuation", "thesis", "literature", "poem", "poetry", "novel", "author",
    "reading", "comprehension", "vocabulary", "synonym", "antonym"
}


def static_version(filename: str) -> int:
    """Use file modified time so static URLs change whenever files change."""
    file_path = os.path.join(app.static_folder or "static", filename)
    try:
        return int(os.path.getmtime(file_path))
    except OSError:
        return 0


@app.context_processor
def inject_asset_url():
    def asset_url(filename: str) -> str:
        return url_for("static", filename=filename, v=static_version(filename))
    return {"asset_url": asset_url}


def get_subject_from_request() -> str:
    referrer = request.referrer or ""
    path = urlparse(referrer).path.lower()
    if path.endswith("/science"):
        return "science"
    if path.endswith("/history"):
        return "history"
    if path.endswith("/english"):
        return "english"
    return "math"


def is_math_related_text(text: str) -> bool:
    lowered = (text or "").lower()
    if not lowered:
        return False
    if any(ch in lowered for ch in "+-*/=^%()[]{}<>"):
        return True
    if any(char.isdigit() for char in lowered):
        return True
    return any(word in lowered for word in MATH_KEYWORDS)


def is_topic_related_text(text: str, subject: str) -> bool:
    lowered = (text or "").lower().strip()
    if not lowered:
        return False

    if subject == "math":
        return is_math_related_text(lowered)
    if subject == "science":
        return any(word in lowered for word in SCIENCE_KEYWORDS)
    if subject == "history":
        return any(word in lowered for word in HISTORY_KEYWORDS)
    if subject == "english":
        return any(word in lowered for word in ENGLISH_KEYWORDS)
    return False


def topic_score(text: str, keywords: set) -> int:
    lowered = (text or "").lower()
    return sum(1 for word in keywords if word in lowered)


def should_reject_for_subject(text: str, subject: str) -> bool:
    """
    Soft gate:
    - Allow if message matches current subject.
    - Allow ambiguous/general school questions.
    - Reject only when another subject is clearly dominant.
    """
    lowered = (text or "").lower().strip()
    if not lowered:
        return False

    scores = {
        "math": topic_score(lowered, MATH_KEYWORDS),
        "science": topic_score(lowered, SCIENCE_KEYWORDS),
        "history": topic_score(lowered, HISTORY_KEYWORDS),
        "english": topic_score(lowered, ENGLISH_KEYWORDS),
    }

    current_score = scores.get(subject, 0)
    best_subject = max(scores, key=scores.get)
    best_score = scores[best_subject]

    if current_score > 0:
        return False
    if best_score == 0:
        return False

    # Only reject when a different subject is clearly indicated.
    return best_subject != subject and best_score >= 2


def get_chat_history(client_id: str, subject: str):
    user_sessions = chat_sessions.setdefault(client_id, {})
    return user_sessions.setdefault(subject, [])


@app.after_request
def add_no_cache_headers(response):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

# =========================
# TEXT CHAT ROUTE
# =========================
@app.route("/chat", methods=["POST"])
def chat():
    payload = request.get_json(silent=True) or {}
    user_message = payload.get("message", "").strip()
    client_id = request.remote_addr or "default"
    subject = get_subject_from_request()

    if not user_message:
        return jsonify({"reply": "Please type a message."})
    if should_reject_for_subject(user_message, subject):
        return jsonify({"reply": f"I only answer {subject}-related questions on this page. Please ask a {subject} question."})

    session = image_sessions.get(client_id)
    history = get_chat_history(client_id, subject)
    if subject == "math" and session:
        return jsonify({
            "reply": (
                "Please upload a photo of your written work for the current step so I can verify it "
                "before giving the next step."
            )
        })

    try:
        messages = [{"role": "system", "content": SUBJECT_SYSTEM_PROMPTS[subject]}]
        messages.extend(history)
        messages.append({"role": "user", "content": user_message})

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages
        )

        ai_reply = (response.choices[0].message.content or "").strip()

        history.append({"role": "user", "content": user_message})
        history.append({"role": "assistant", "content": ai_reply})
        if len(history) > MAX_HISTORY_MESSAGES:
            del history[:-MAX_HISTORY_MESSAGES]

        return jsonify({"reply": ai_reply})

    except Exception as e:
        print("ERROR:", e)
        return jsonify({"reply": "Something went wrong."})


# =========================
# IMAGE ROUTE
# =========================
@app.route("/upload-image", methods=["POST"])
def upload_image():
    file = request.files.get("image")
    prompt = request.form.get("prompt", "").strip()
    client_id = request.remote_addr or "default"
    subject = get_subject_from_request()

    if not file:
        return jsonify({"reply": "No image uploaded."})

    try:
        image_bytes = file.read()
        base64_image = base64.b64encode(image_bytes).decode("utf-8")
        mime_type = file.mimetype or "image/png"
        prompt_text = prompt or ""
        image_data_url = f"data:{mime_type};base64,{base64_image}"
        session = image_sessions.get(client_id)

        if subject != "math":
            subject_prompt = prompt_text or f"Answer the {subject} homework question shown in this image."
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": SUBJECT_SYSTEM_PROMPTS[subject]},
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": subject_prompt},
                            {"type": "image_url", "image_url": {"url": image_data_url}}
                        ]
                    }
                ]
            )

            content = response.choices[0].message.content
            if isinstance(content, list):
                ai_reply = " ".join(
                    part.get("text", "") if isinstance(part, dict) else str(part)
                    for part in content
                ).strip()
            else:
                ai_reply = (content or "").strip()

            if not ai_reply:
                ai_reply = f"I couldn't read a clear {subject} question. Please upload a clearer image."
            return jsonify({"reply": ai_reply})

        if session:
            step_index = session["step_index"]
            expected_step = session["steps"][step_index]
            verify_prompt = (
                "You are checking whether a student completed a math step.\n"
                f"Expected step: {expected_step}\n\n"
                "Look at the uploaded image. Reply with exactly one word first: YES or NO.\n"
                "Then add one short sentence of feedback."
            )

            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": verify_prompt},
                        {"type": "image_url", "image_url": {"url": image_data_url}}
                    ]
                }]
            )
            content = response.choices[0].message.content
            if isinstance(content, list):
                verdict_text = " ".join(
                    part.get("text", "") if isinstance(part, dict) else str(part)
                    for part in content
                ).strip()
            else:
                verdict_text = (content or "").strip()

            normalized = verdict_text.upper()
            if not normalized.startswith("YES"):
                return jsonify({
                    "reply": (
                        "I can't confirm this step yet. Please rewrite this exact step clearly and upload another photo:\n"
                        f"Step {step_index + 1}: {expected_step}"
                    )
                })

            next_index = step_index + 1
            if next_index >= len(session["steps"]):
                final_answer = session.get("final_answer", "").strip()
                image_sessions.pop(client_id, None)
                if final_answer:
                    return jsonify({
                        "reply": (
                            "Great job. All steps are verified.\n"
                            f"Final answer: {final_answer}"
                        )
                    })
                return jsonify({"reply": "Great job. All steps are verified."})

            session["step_index"] = next_index
            return jsonify({
                "reply": (
                    f"Nice work. Step {next_index} is verified.\n"
                    f"Step {next_index + 1}: {session['steps'][next_index]}\n"
                    "Write this on your homework, then upload a new photo."
                )
            })

        planning_prompt = (
            "Solve only if this is a math homework problem.\n"
            "Return valid JSON with this exact schema:\n"
            "{"
            "\"is_math\": boolean, "
            "\"steps\": [\"short step 1\", \"short step 2\"], "
            "\"final_answer\": \"text\", "
            "\"message\": \"used when is_math is false\""
            "}\n"
            "Rules:\n"
            "- If not math, set is_math false and provide message asking for a math problem.\n"
            "- If math, set is_math true, provide concise steps in order, and final_answer.\n"
            "- Keep each step short and actionable."
        )

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            response_format={"type": "json_object"},
            messages=[{
                "role": "system",
                "content": SUBJECT_SYSTEM_PROMPTS["math"]
            }, {
                "role": "user",
                "content": [
                    {"type": "text", "text": planning_prompt},
                    {"type": "text", "text": f"User prompt: {prompt_text}" if prompt_text else "User prompt: (none)"},
                    {"type": "image_url", "image_url": {"url": image_data_url}}
                ]
            }]
        )

        content = response.choices[0].message.content
        if isinstance(content, list):
            raw_json = " ".join(
                part.get("text", "") if isinstance(part, dict) else str(part)
                for part in content
            ).strip()
        else:
            raw_json = (content or "").strip()

        payload = json.loads(raw_json) if raw_json else {}
        if not payload.get("is_math"):
            return jsonify({"reply": payload.get("message", "Please upload a math homework problem.")})

        steps = payload.get("steps") or []
        if not isinstance(steps, list):
            steps = []
        steps = [str(step).strip() for step in steps if str(step).strip()]
        if not steps:
            return jsonify({"reply": "I couldn't read a clear math problem. Please upload a clearer image."})

        image_sessions[client_id] = {
            "steps": steps,
            "step_index": 0,
            "final_answer": str(payload.get("final_answer", "")).strip(),
        }

        return jsonify({
            "reply": (
                f"Step 1: {steps[0]}\n"
                "Write this on your homework, then upload a new photo so I can verify before step 2."
            )
        })

    except Exception as e:
        print("IMAGE ERROR:", e)
        if app.debug:
            return jsonify({"reply": f"Image processing failed: {str(e)}"})
        return jsonify({"reply": "Something went wrong processing the image."})


# =========================
# HOME
# =========================
@app.route("/")
def home():
    return render_template("chat.html")


@app.route("/science")
def science_page():
    return render_template("science.html")


@app.route("/history")
def history_page():
    return render_template("history.html")


@app.route("/english")
def english_page():
    return render_template("english.html")


if __name__ == "__main__":
    app.run(debug=True)
