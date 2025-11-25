let session = [];
let first = null;

window.onload = () => {
    first = sessionStorage.getItem("first");
    const persona = sessionStorage.getItem("persona");

    if (persona) {
        session.push({role: "user", parts: [persona]});
    }
    if (first) {
        addMessage("dog", first);
        session.push({role: "model", parts: [first]});
    }
};

function addMessage(role, text) {
    const chat = document.getElementById("chatbox");
    const div = document.createElement("div");
    div.className = role === "user" ? "user_msg" : "dog_msg";
    div.innerText = text;
    chat.appendChild(div);
    chat.scrollTop = chat.scrollHeight;
}

async function send() {
    const input = document.getElementById("msg");
    const msg = input.value.trim();
    if (!msg) return;

    addMessage("user", msg);
    input.value = "";

    try {
        const res = await fetch("/api/chat", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({ session, message: msg })
        });
        const json = await res.json();
        addMessage("dog", json.reply);
        session = json.session || session;
    } catch (e) {
        addMessage("dog", "지금은 연결이 살짝 불안한가봐... 조금 있다가 다시 이야기해볼까?");
    }
}

function enter(event) {
    if (event.key === "Enter") {
        send();
    }
}
