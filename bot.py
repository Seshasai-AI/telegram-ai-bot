import os
import logging
from dotenv import load_dotenv
from groq import Groq
from tavily import TavilyClient
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    MessageHandler,
    CommandHandler,
    filters,
    ContextTypes
)
from collections import defaultdict
from datetime import date

load_dotenv()
BOT_TOKEN      = os.getenv("BOT_TOKEN")
GROQ_API_KEY   = os.getenv("GROQ_API_KEY")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")

groq_client   = Groq(api_key=GROQ_API_KEY)
tavily_client = TavilyClient(api_key=TAVILY_API_KEY)

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

chat_history = defaultdict(list)
TODAY = date.today().strftime("%B %d, %Y")

LIVE_KEYWORDS = [
    "today", "now", "current", "latest", "live",
    "score", "match", "ipl", "cricket", "weather",
    "price", "news", "stock", "rate", "winner",
    "result", "update", "2024", "2025", "2026",
    "yesterday", "this week", "trending",
    "who won", "what happened", "points table"
]

def get_web_results(query):
    try:
        direct = tavily_client.qna_search(query=query)
        results = tavily_client.search(
            query=query,
            max_results=5,
            search_depth="advanced"
        )
        context  = f"=== DIRECT ANSWER ===\n{direct}\n\n"
        context += f"=== WEB SOURCES ===\n"
        for i, r in enumerate(results["results"], 1):
            context += (
                f"Source {i}: {r['title']}\n"
                f"URL: {r['url']}\n"
                f"Info: {r['content'][:400]}\n\n"
            )
        return context
    except Exception as e:
        logging.error(f"Tavily error: {e}")
        return ""

def ask_groq(user_name, history, extra=""):
    response = groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {
                "role": "system",
                "content": (
                    f"You are a highly accurate AI assistant. "
                    f"User name is {user_name}. "
                    f"Today is {TODAY}.\n\n"
                    f"RULES:\n"
                    f"1. If web results are provided below, "
                    f"use ONLY that data to answer\n"
                    f"2. Never guess or make up facts\n"
                    f"3. Always give clear structured answers\n"
                    f"4. Mention source URL when available\n\n"
                    f"{extra}"
                )
            },
            *history
        ],
        temperature=0.2
    )
    return response.choices[0].message.content

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.effective_user.first_name
    await update.message.reply_text(
        f"Hello {name}! I am your Smart AI Assistant.\n\n"
        f"Powered by:\n"
        f"- Tavily → live web search\n"
        f"- Llama 3.3 → fast accurate answers\n\n"
        f"Ask me anything!\n\n"
        f"Commands:\n"
        f"/start  - Welcome\n"
        f"/help   - How to use\n"
        f"/clear  - Clear memory\n"
        f"/search - Force web search"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "How I work:\n\n"
        "Live questions (scores, news, weather)\n"
        "→ I search web first then give accurate answer\n\n"
        "General questions\n"
        "→ I answer from my AI knowledge\n\n"
        "Commands:\n"
        "/search your question → force web search\n"
        "/clear → reset conversation memory"
    )

async def clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_history[user_id].clear()
    await update.message.reply_text(
        "Memory cleared! Fresh start."
    )

async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = " ".join(context.args)
    if not query:
        await update.message.reply_text(
            "Usage: /search IPL 2026 points table"
        )
        return
    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id,
        action="typing"
    )
    await update.message.reply_text(
        f"Searching web for: {query}..."
    )
    search_context = get_web_results(query)
    if not search_context:
        await update.message.reply_text(
            "Could not fetch results. Try again!"
        )
        return
    try:
        reply = ask_groq(
            update.effective_user.first_name,
            [{"role": "user", "content": query}],
            extra=search_context
        )
        await update.message.reply_text(reply)
    except Exception as e:
        logging.error(e)
        await update.message.reply_text(
            "Something went wrong. Try again!"
        )

async def ai_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id   = update.effective_user.id
    user_name = update.effective_user.first_name
    user_text = update.message.text

    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id,
        action="typing"
    )

    search_context = ""
    if any(w in user_text.lower() for w in LIVE_KEYWORDS):
        await update.message.reply_text(
            "Searching web for latest info..."
        )
        search_context = get_web_results(user_text)

    chat_history[user_id].append({
        "role": "user",
        "content": user_text
    })
    history = chat_history[user_id][-10:]

    try:
        reply = ask_groq(user_name, history, search_context)
        chat_history[user_id].append({
            "role": "assistant",
            "content": reply
        })
        await update.message.reply_text(reply)

    except Exception as e:
        logging.error(f"Error: {e}")
        await update.message.reply_text(
            "Sorry something went wrong. Please try again!"
        )

def main():
    print("Smart AI Bot starting...")
    print(f"Today: {TODAY}")
    print("Groq + Tavily active!")
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start",  start))
    app.add_handler(CommandHandler("help",   help_command))
    app.add_handler(CommandHandler("clear",  clear_command))
    app.add_handler(CommandHandler("search", search_command))
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND, ai_reply
    ))
    print("Bot is running! Press Ctrl+C to stop.")
    app.run_polling()

if __name__ == "__main__":
    main()