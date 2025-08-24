import discord
from discord import app_commands
from discord.ext import commands
import yt_dlp as youtube_dl
import asyncio
import spotipy

intents = discord.Intents.default()
intents.message_content = True

class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="e!", intents=intents, reconnect=True)
        self.song_queues = {}

    def get_queue(self, guild_id):
        if guild_id not in self.song_queues:
            self.song_queues[guild_id] = []
        return self.song_queues[guild_id]

    async def setup_hook(self):
        await self.tree.sync()


    def get_queue(self, guild_id):
        if guild_id not in self.song_queues:
            self.song_queues[guild_id] = []
        return self.song_queues[guild_id]

    async def setup_hook(self):
        await self.tree.sync()

bot = MyBot()

class RobustVoiceClient(discord.VoiceClient):
    async def connect_websocket(self):
        try:
            await super().connect_websocket()
        except discord.ConnectionClosed as e:
            print(f"WebSocket connection error: {e.code}")
            await self.disconnect(force=True)
            raise

ytdl_format_options = {
    'format': 'bestaudio[ext=m4a]/bestaudio/best',
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0',
    'socket_timeout': 30,
    'noplaylist': True,
}

ffmpeg_options = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -loglevel error',
    'options': '-vn',
    'executable': r'C:\\ffmpeg\\ffmpeg.exe'  
}

print("Electro Guitar Sistemi")

ytdl = youtube_dl.YoutubeDL(ytdl_format_options)

class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get('title')
        self.url = data.get('url')

    @classmethod
    async def from_url(cls, url, *, loop=None, stream=False):
        loop = loop or asyncio.get_event_loop()
        for attempt in range(3):
            try:
                data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=not stream))
                if not data:
                    raise Exception("Video information could not be retrieved")
                if 'entries' in data:
                    data = data['entries'][0]
                filename = data['url'] if stream else ytdl.prepare_filename(data)
                return cls(discord.FFmpegPCMAudio(filename, **ffmpeg_options), data=data)
            except Exception as e:
                if attempt == 2:
                    raise

async def safe_connect(ctx):
    for attempt in range(3):
        try:
            if not ctx.voice_client:
                vc = await ctx.author.voice.channel.connect(cls=RobustVoiceClient, timeout=30.0)
            else:
                vc = ctx.voice_client
                if vc.channel != ctx.author.voice.channel:
                    await vc.move_to(ctx.author.voice.channel)
            if not hasattr(vc, 'is_connected') or not vc.is_connected():
                raise ConnectionError("Connection verification failed")
            return vc
        except Exception:
            if attempt == 2:
                raise

@bot.event
async def on_voice_state_update(member, before, after):
    if member == bot.user and before.channel and not after.channel:
        print("Bot kicked from voice channel")

def play_next(ctx, vc):
    queue = bot.get_queue(ctx.guild.id)
    if queue:
        next_source = queue.pop(0)
        vc.play(next_source, after=lambda e: play_next(ctx, vc))
        asyncio.run_coroutine_threadsafe(
            ctx.send(f"🎶 Now playing: {next_source.title}"), bot.loop
        )
    else:
        asyncio.run_coroutine_threadsafe(vc.disconnect(), bot.loop)

@bot.command()
async def play(ctx, *, search: str):
    if not ctx.author.voice:
        return await ctx.send("🎤 You must be in a voice channel first!")

    vc = await safe_connect(ctx)

    async with ctx.typing():
        if not search.startswith(('http://', 'https://')):
            search = f"ytsearch:{search}"

        try:
            player = await YTDLSource.from_url(search, loop=bot.loop, stream=True)
        except Exception as e:
            return await ctx.send(f"❌ Failed to load audio: {e}")

        queue = bot.get_queue(ctx.guild.id)

        if not vc.is_playing() and not vc.is_paused():
            vc.play(player, after=lambda e: play_next(ctx, vc))
            # Şarkı arka planda başlıyor, mesajı anında gönderiyoruz
            await ctx.send(f"🎶 Now playing: **{player.title}**")
        else:
            queue.append(player)
            await ctx.send(f"➕ Added to queue: **{player.title}**")

@bot.command()
async def queue(ctx):
    queue = bot.get_queue(ctx.guild.id)
    if not queue:
        return await ctx.send("📭 The queue is empty.")
    msg = '\n'.join([f"{i+1}. {song.title}" for i, song in enumerate(queue)])
    await ctx.send(f"📜 Queue:\n{msg}")

@bot.command()
async def pause(ctx):
    vc = ctx.voice_client
    if not vc or not vc.is_playing():
        return await ctx.send("Nothing is playing.")
    vc.pause()
    await ctx.send("⏸️ Playback paused.")

@bot.command()
async def resume(ctx):
    vc = ctx.voice_client
    if not vc or not vc.is_connected():
        return await ctx.send("Bot is not in a voice channel.")
    if not vc.is_paused():
        return await ctx.send("Nothing is paused.")
    vc.resume()
    await ctx.send("▶️ Playback resumed.")

@bot.command()
async def stop(ctx):
    vc = ctx.voice_client
    if not vc or not vc.is_connected():
        return await ctx.send("Bot is not in a voice channel.")
    queue = bot.get_queue(ctx.guild.id)
    queue.clear()
    if vc.is_playing() or vc.is_paused():
        vc.stop()
        await ctx.send("⏹️ Playback stopped.")
    else:
        await ctx.send("🚫 Nothing is playing.")

@bot.command()
async def leave(ctx):
    vc = ctx.voice_client
    if not vc or not vc.is_connected():
        return await ctx.send("Bot is not in a voice channel.")
    queue = bot.get_queue(ctx.guild.id)
    queue.clear()
    await vc.disconnect()
    await ctx.send("👋 Bot has left the voice channel.")

@bot.command()
async def skip(ctx):
    vc = ctx.voice_client
    if not vc or not vc.is_connected():
        return await ctx.send("Bot is not in a voice channel.")
    queue = bot.get_queue(ctx.guild.id)
    if queue:
        if vc.is_playing() or vc.is_paused():
            vc.stop()
        await ctx.send("⏭️ Skipped.")
    else:
        await ctx.send("⚠️ No songs in queue to skip.")

@bot.tree.command(name="help", description="Show bot commands")
async def slash_help(interaction: discord.Interaction):
    embed = discord.Embed(title="🎵 Bot Commands", color=discord.Color.blue())
    embed.add_field(name="e!play <song/URL>", value="Play a song or add it to the queue.", inline=False)
    embed.add_field(name="e!pause", value="Pause the currently playing song.", inline=False)
    embed.add_field(name="e!resume", value="Resume the paused song.", inline=False)
    embed.add_field(name="e!stop", value="Stop the music but stay in the voice channel.", inline=False)
    embed.add_field(name="e!leave", value="Make the bot leave the voice channel.", inline=False)
    embed.add_field(name="e!queue", value="Show the current song queue.", inline=False)
    embed.add_field(name="e!skip", value="Skip the current song.", inline=False)
    embed.add_field(name="e!fixvc", value="Reset the voice connection.", inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=True)

bot.run('MTQwNzAyMjQ1Nzc2Nzg1ODI2Ng.GStX8K.3Dvku0m7yz8GbAhHxq3d-RIFsT0rASrUvEbDDo')
