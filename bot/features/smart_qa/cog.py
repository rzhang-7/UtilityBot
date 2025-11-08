from discord.ext import commands
import discord
import random
from typing import List, Tuple, Optional
import logging
import os
import aiohttp

# Chroma could be implemented to support semantic search on large files if needed
#_DISABLE_CHROMA = os.getenv("DISABLE_CHROMA", "").lower() in {"1","true","yes","on"}

logger = logging.getLogger("utilitybot.smart_qa")

def _get_knowledge_document() -> str:
    '''Mock knowledge base. Will be replaced by an actual document in the future.'''
    return (
        "Electrium Mobility is a student design team based at the University of Waterloo. Its goal is to create sustainable and affordable transportation in the form of Personal Electric Vehicles."
        "UtilityBot is a modular Discord bot written in Python using discord.py. "
        "Features are implemented as Cogs and are auto-loaded from bot/features. "
        "The Smart Q&A module answers user questions by consulting relevant notes. "
        "Commands use the '!' prefix (e.g., !qa). Message content intent must be enabled. "
        "Environment variables are provided via a .env file (DISCORD_TOKEN). "
        "Logging is configured through bot/core/logging.py. "
        "To run the bot: activate the venv and execute `python -m bot.main`. "
        "Extensions are discovered and loaded by bot/core/loader.py. "
        "This is a mock knowledge base used only for development without external APIs."
    )

async def _ask_deepseek(question: str, knowledge_document: str) -> Optional[str]:
    """Ask DeepSeek with knowledge context. Returns answer or None on failure."""
    api_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
    if not api_key:
        return None

    url = "https://api.deepseek.com/v1/chat/completions"
    payload = {
        "model": "deepseek-chat",
        "temperature": 0.2,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a helpful assistant. Answer strictly using the provided knowledge. "
                    "If the answer is not present, say: 'I don't know based on the provided knowledge.'"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Knowledge:\n{knowledge_document}\n\n"
                    f"Question:\n{question}\n\n"
                    "Answer in 1-2 concise sentences."
                ),
            },
        ],
    }

    # Standard header
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as session:
            async with session.post(url, json=payload, headers=headers) as resp:
                if resp.status != 200:
                    logger.warning("DeepSeek API non-200: %s", resp.status)
                    return None

                # Handles none type at each level
                data = await resp.json()
                choices = (data or {}).get("choices") or []
                if not choices:
                    return None
                content = (((choices[0] or {}).get("message") or {}).get("content") or "").strip()

                return content or None
    except Exception:
        logger.exception("DeepSeek API call failed")
        return None
import aiohttp
import os

class SmartQACog(commands.Cog):
    """Smart Q&A feature implementation."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # get API info
        self.api_url = os.getenv("OUTLINE_API_URL")
        self.api_token = os.getenv("OUTLINE_API_KEY")

    @commands.command(name="qa")
    async def qa(self, ctx: commands.Context, *, question: str):
        """Placeholder command: accept a question and return a placeholder response."""
        await ctx.send(f"Received question: {question}\n(Placeholder response, to be implemented)")

    async def _fetch_collections(self):
        """Fetch all collections."""
        headers = {"Authorization": f"Bearer {self.api_token}"}
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{self.api_url}/collections.list", headers=headers) as resp:
                res = await resp.json()
                return res.get("data", [])

    async def _fetch_documents(self, collection_id):
        """Fetch all documents in a collection (recursively)."""
        headers = {"Authorization": f"Bearer {self.api_token}"}
        data = {"collectionId": collection_id}

        async with aiohttp.ClientSession() as session:
            async with session.post(f"{self.api_url}/documents.list", headers=headers, json=data) as resp:
                res = await resp.json()
                return res.get("data", [])




    def _get_full_path(self, doc, by_id):
        """Gets full path of document, separated by '/'"""
        parts = [doc.get("title")] # get title of each document and store in array `parts`
        parent_id = doc.get("parentDocumentId") # get parent id of each document
        
        while parent_id: # while we havent reached root
            parent = by_id.get(parent_id) # find curr document's parent using id 
                                          # (pass parent_id as key in by_id)
            parts.append(parent["title"]) # add title of parent to path
            parent_id = parent.get("parentDocumentId") # set new parent id as the parent_id 
                                                       # of curr document

        parts.reverse() # reverse titles (path is from root to document, but its the other way
                        # around since we found it recursively)

        return "/".join(parts) # join titles with '/', then return it

    @commands.command(name="docs")
    async def get_bottom_docs(self, ctx):
        """List bottom-level documents after interactively selecting a collection."""

        # Fetch collections
        collections = await self._fetch_collections() # get all collections
        if not collections: # there are no collections
            return await ctx.send("No collections found.")

        # Display collections
        msg = "**Select a collection by name:**\n"
        for i, c in enumerate(collections, start=1):
            msg += f"{i}. {c['name']}\n" # display "number. title"

        await ctx.send(msg)

        # Wait for user reply
        def check(m):
            # must be same discord user and same channel
            return m.author == ctx.author and m.channel == ctx.channel 

        # give 30 sec time limit for user response
        try:  
            reply = await self.bot.wait_for("message", check=check, timeout=30) 
        except TimeoutError:
            return await ctx.send("Timed out waiting for a response.")

        name = str(reply.content) # user reply (name of collection)
        found = 0
        index = 0
        # Find collection based on name
        for collection in collections:
            if collection['name'] == name:
                found = 1
                break
            index+=1
        
        if not found: # Didn't find collection
            return await ctx.send("Invalid collection name. Please try again.")
        
        selected = collections[index]
        # await ctx.send(f"{index}") # debug
        collection_id = selected["id"]
        collection_name = selected["name"]

        await ctx.send(f"Fetching bottom-level documents from **{collection_name}**...")

        # Fetch documents
        docs = await self._fetch_documents(collection_id) # get all documents inside collection
        
        if not docs: # no documents in collection
            return await ctx.send("No documents found in this collection.")
        
        # Find bottom-level docs and get its full path

        count = len(docs) # number of documents
        
        by_id = {doc["id"]: doc for doc in docs} # dictionary map id to doc (key : value) for each document 
        response = f"**{count} bottom-level documents found in {collection_name}:**\n"
        
        for doc in docs: # get full path of all documents
            response += f"- {self._get_full_path(doc, by_id)}\n"

        await ctx.send(response) # print full path of all documents 


async def setup(bot: commands.Bot):
    await bot.add_cog(SmartQACog(bot))