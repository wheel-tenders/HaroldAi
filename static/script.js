let isSending = false;

function formatMathSymbols(text) {
    if (!text) return text;

    let formatted = text;

    // Convert common LaTeX wrappers and commands to plain-symbol math.
    formatted = formatted
        .replace(/\\\[((?:.|\n)*?)\\\]/g, "$1")
        .replace(/\\\(((?:.|\n)*?)\\\)/g, "$1")
        .replace(/\$\$((?:.|\n)*?)\$\$/g, "$1")
        .replace(/\$([^$\n]+)\$/g, "$1")
        .replace(/\\\\/g, "\n")
        .replace(/\\frac\s*\{([^{}]+)\}\s*\{([^{}]+)\}/g, "$1/$2")
        .replace(/\\sqrt\s*\{([^{}]+)\}/g, "√$1")
        .replace(/\\times/g, "×")
        .replace(/\\cdot/g, "·")
        .replace(/\\div/g, "÷")
        .replace(/\\leq/g, "≤")
        .replace(/\\geq/g, "≥")
        .replace(/\\neq/g, "≠")
        .replace(/\\approx/g, "≈")
        .replace(/\\pm/g, "±")
        .replace(/\\infty/g, "∞")
        .replace(/\\pi/g, "π")
        .replace(/\\theta/g, "θ")
        .replace(/\\delta/g, "∆")
        .replace(/\\sum/g, "∑")
        .replace(/\\int/g, "∫")
        .replace(/\\partial/g, "∂")
        .replace(/\\\{/g, "{")
        .replace(/\\\}/g, "}")
        .replace(/\\,/g, " ")
        .replace(/\\;/g, " ")
        .replace(/\\:/g, " ")
        .replace(/\\!/g, "");

    const replacements = [
        [/\bpi\b/gi, "π"],
        [/\btheta\b/gi, "θ"],
        [/\bdelta\b/gi, "∆"],
        [/\binfty\b/gi, "∞"],
        [/\binfinity\b/gi, "∞"],
        [/\bsum\b/gi, "∑"],
        [/\bintegral\b/gi, "∫"],
        [/\bpartial\b/gi, "∂"],
        [/\bdeg\b/gi, "°"],
        [/!=/g, "≠"],
        [/>=/g, "≥"],
        [/<=/g, "≤"],
        [/\+\/-/g, "±"],
        [/\bsqrt\s*\(/gi, "√("],
    ];

    replacements.forEach(([pattern, symbol]) => {
        formatted = formatted.replace(pattern, symbol);
    });

    // Normalize common ASCII operators when used between numbers/variables.
    formatted = formatted
        .replace(/([0-9A-Za-z)\]])\s*\*\s*([0-9A-Za-z([])/g, "$1 × $2")
        .replace(/([0-9A-Za-z)\]])\s*\/\s*([0-9A-Za-z([])/g, "$1 ÷ $2");

    return formatted;
}

function send() {
    const input = document.getElementById("userInput");
    const fileInput = document.getElementById("imageInput");
    const chatbox = document.getElementById("chatbox");
    const sendBtn = document.getElementById("sendBtn");
    const imageBtn = document.getElementById("imageBtn");
    const voiceBtn = document.getElementById("voiceBtn");

    const message = input.value.trim();
    const file = fileInput.files[0];

    if (isSending || (!message && !file)) return;

    if (voiceBtn && voiceBtn.classList.contains("voice-active")) {
        voiceBtn.click();
    }

    if (message) {
        appendTextMessage(chatbox, "user", message);
    }

    if (file) {
        appendImageMessage(chatbox, file);
    }

    let task = null;
    if (file) {
        task = sendImage(file, message);
    } else if (message) {
        task = sendText(message);
    }

    isSending = true;
    input.disabled = true;
    sendBtn.disabled = true;
    imageBtn.disabled = true;
    if (voiceBtn) {
        voiceBtn.disabled = true;
    }
    const thinkingBubble = appendThinkingMessage(chatbox);

    task
        .then((data) => {
            removeMessage(thinkingBubble);
            appendTextMessage(chatbox, "ai", formatMathSymbols(`Harold: ${data.reply}`), { animate: true });
        })
        .catch(() => {
            removeMessage(thinkingBubble);
            appendTextMessage(chatbox, "ai", "Harold: Something went wrong.");
        })
        .finally(() => {
            isSending = false;
            input.disabled = false;
            sendBtn.disabled = false;
            imageBtn.disabled = false;
            if (voiceBtn) {
                voiceBtn.disabled = false;
            }
            input.focus();
        });

    input.value = "";
    fileInput.value = "";
}

function appendTextMessage(chatbox, roleClass, text, options = {}) {
    const messageEl = document.createElement("div");
    messageEl.className = `message ${roleClass}`;
    if (options.animate && roleClass === "ai") {
        messageEl.textContent = "";
        typeMessage(messageEl, text, chatbox);
    } else {
        messageEl.textContent = text;
    }
    chatbox.appendChild(messageEl);
    chatbox.scrollTop = chatbox.scrollHeight;
}

function appendThinkingMessage(chatbox) {
    const messageEl = document.createElement("div");
    messageEl.className = "message ai ai-thinking";
    messageEl.innerHTML = "Harold is thinking<span class=\"dot\">.</span><span class=\"dot\">.</span><span class=\"dot\">.</span>";
    chatbox.appendChild(messageEl);
    chatbox.scrollTop = chatbox.scrollHeight;
    return messageEl;
}

function removeMessage(el) {
    if (el && el.parentNode) {
        el.parentNode.removeChild(el);
    }
}

function typeMessage(el, text, chatbox) {
    const chars = Array.from(text);
    let index = 0;
    const timer = setInterval(() => {
        index = Math.min(index + 1, chars.length);
        el.textContent = chars.slice(0, index).join("");
        chatbox.scrollTop = chatbox.scrollHeight;
        if (index >= chars.length) {
            clearInterval(timer);
        }
    }, 28);
}

function appendImageMessage(chatbox, file) {
    const container = document.createElement("div");
    container.className = "message user";
    const img = document.createElement("img");
    img.style.maxWidth = "200px";
    img.style.borderRadius = "8px";
    img.src = URL.createObjectURL(file);
    img.onload = () => URL.revokeObjectURL(img.src);
    container.appendChild(img);
    chatbox.appendChild(container);
    chatbox.scrollTop = chatbox.scrollHeight;
}

function sendText(message) {
    return fetch("/chat", {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify({ message })
    }).then(handleJsonResponse);
}

function sendImage(file, prompt) {
    const formData = new FormData();
    formData.append("image", file);
    if (prompt) formData.append("prompt", prompt);

    return fetch("/upload-image", {
        method: "POST",
        body: formData
    }).then(handleJsonResponse);
}

async function handleJsonResponse(res) {
    if (res.status === 401) {
        let payload = {};
        try {
            payload = await res.json();
        } catch (err) {
            payload = {};
        }
        window.location.href = payload.redirect || "/login";
        throw new Error("Unauthorized");
    }

    if (!res.ok) {
        throw new Error(`Request failed with status ${res.status}`);
    }
    return res.json();
}

function setSidebarState(layout, toggleBtn, isOpen) {
    layout.classList.toggle("sidebar-closed", !isOpen);
    toggleBtn.setAttribute("aria-expanded", String(isOpen));
    toggleBtn.textContent = isOpen ? "◀" : "▶";
    toggleBtn.setAttribute("aria-label", isOpen ? "Collapse sidebar" : "Expand sidebar");
    localStorage.setItem("sidebarOpen", String(isOpen));
}

function setTheme(themeName) {
    document.body.setAttribute("data-theme", themeName);
    localStorage.setItem("themeName", themeName);
}

function insertAtCursor(input, text) {
    const start = input.selectionStart ?? input.value.length;
    const end = input.selectionEnd ?? input.value.length;
    const nextValue = input.value.slice(0, start) + text + input.value.slice(end);
    input.value = nextValue;
    const nextCursor = start + text.length;
    input.setSelectionRange(nextCursor, nextCursor);
    input.focus();
}

document.addEventListener("DOMContentLoaded", function () {

    const input = document.getElementById("userInput");
    const sendBtn = document.getElementById("sendBtn");
    const imageBtn = document.getElementById("imageBtn");
    const voiceBtn = document.getElementById("voiceBtn");
    const imageInput = document.getElementById("imageInput");
    const layout = document.getElementById("layout");
    const sidebarToggle = document.getElementById("sidebarToggle");
    const themeSelect = document.getElementById("themeSelect");
    const logoutBtn = document.getElementById("logoutBtn");

    const savedSidebarState = localStorage.getItem("sidebarOpen") === "true";
    setSidebarState(layout, sidebarToggle, savedSidebarState);

    const savedThemeName = localStorage.getItem("themeName") || "ocean";
    setTheme(savedThemeName);
    if (themeSelect) {
        themeSelect.value = savedThemeName;
        themeSelect.addEventListener("change", function () {
            setTheme(themeSelect.value);
        });
    }

    sidebarToggle.addEventListener("click", function () {
        const isOpen = sidebarToggle.getAttribute("aria-expanded") === "true";
        setSidebarState(layout, sidebarToggle, !isOpen);
    });

    if (logoutBtn) {
        logoutBtn.addEventListener("click", async function () {
            try {
                await fetch("/auth/logout", { method: "POST" });
            } catch (err) {
                // Redirect regardless so user is returned to login even if request fails.
            } finally {
                window.location.href = "/login";
            }
        });
    }

    sendBtn.addEventListener("click", send);

    input.addEventListener("keydown", function (event) {
        if (event.key === "Enter") {
            event.preventDefault();
            send();
        }
    });

    imageBtn.addEventListener("click", function () {
        imageInput.click();
    });

    if (voiceBtn) {
        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
        if (!SpeechRecognition) {
            voiceBtn.disabled = true;
            voiceBtn.title = "Voice input is not supported in this browser.";
        } else {
            const recognition = new SpeechRecognition();
            recognition.lang = navigator.language || "en-US";
            recognition.interimResults = false;
            recognition.maxAlternatives = 1;
            recognition.continuous = false;

            function setVoiceState(isActive) {
                voiceBtn.classList.toggle("voice-active", isActive);
                voiceBtn.textContent = isActive ? "Stop" : "Voice";
            }

            recognition.onresult = function (event) {
                let transcript = "";
                for (let i = event.resultIndex; i < event.results.length; i += 1) {
                    transcript += event.results[i][0].transcript || "";
                }
                transcript = transcript.trim();
                if (!transcript) return;

                const needsSpace = input.value && !input.value.endsWith(" ");
                input.value = `${input.value}${needsSpace ? " " : ""}${transcript}`;
                input.focus();
            };

            recognition.onend = function () {
                setVoiceState(false);
            };

            recognition.onerror = function () {
                setVoiceState(false);
            };

            voiceBtn.addEventListener("click", function () {
                if (isSending) return;
                const isActive = voiceBtn.classList.contains("voice-active");
                if (isActive) {
                    recognition.stop();
                    return;
                }
                setVoiceState(true);
                recognition.start();
            });
        }
    }

    document.querySelectorAll(".math-symbol").forEach(function (button) {
        button.addEventListener("click", function () {
            const symbol = button.getAttribute("data-symbol") || "";
            if (!symbol) return;
            insertAtCursor(input, symbol);
        });
    });
});
