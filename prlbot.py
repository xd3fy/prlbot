import os

TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN env var not found!")
import aiohttp
import asyncio
import sys
import discord
import re
import json
from discord import app_commands
from discord.ext import commands
import datetime
import asyncio
from typing import Optional
from discord.ui import Modal, TextInput, View, button



intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)


# Assume 'active_games' is a global dictionary holding active games information
active_games = {}
user_data_file = "user_data_prl.json"

try:
    with open(user_data_file, "r") as f:
        user_data = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
    user_data = {}

class LeagueView(discord.ui.View):
    def __init__(self, host_id, thread_id, hosting_msg_id, thread_msg_id, gametype, matchtype, region, player_cap):
        super().__init__(timeout=None)
        self.host_id = host_id
        self.thread_id = thread_id
        self.hosting_msg_id = hosting_msg_id
        self.thread_msg_id = thread_msg_id
        self.gametype = gametype
        self.matchtype = matchtype
        self.region = region
        self.player_cap = player_cap

    async def add_player(self, interaction: discord.Interaction, user: discord.Member, display_name: str):
        game = active_games.get(self.host_id)
        if not game:
            return await interaction.response.send_message("This game is no longer active.", ephemeral=True)

        if any(player["id"] == user.id for player in game["players"]):
            return await interaction.response.send_message("You're already in this match.", ephemeral=True)

        game["players"].append({"id": user.id, "display_name": display_name})
        thread = interaction.guild.get_thread(self.thread_id)
        if thread:
            await thread.add_user(user)

        region_role = next((r.name for r in user.roles if r.name in ["NA", "EU", "ASIA", "OCE"]), "Not specified")
        rank_role = user_data.get(str(user.id), {}).get("rank", "Unranked")

        join_embed = discord.Embed(
            description=(
                f"{user.mention} has joined the match!\n"
                f"Display Name: {display_name}\n"
                f"Rank: {rank_role}\n"
                f"Region: {region_role}"
            ),
            color=discord.Color.blue()
        )
        await thread.send(embed=join_embed)

        # Update player count in welcome message
        async for msg in thread.history(limit=10, oldest_first=True):
            if msg.embeds and msg.embeds[0].footer and msg.embeds[0].footer.text.startswith("Players:"):
                updated_embed = msg.embeds[0]
                updated_embed.set_footer(text=f"Players: {len(game['players'])}/{self.player_cap}")
                try:
                    await msg.edit(embed=updated_embed)
                except Exception as e:
                    print(f"[Error Updating Welcome Embed] {e}")
                break

        log_channel = interaction.guild.get_channel(1357869099958403072)
        if log_channel:
            uid = str(user.id)
            ign = user_data.get(uid, {}).get("display_name", "Unknown IGN")
            formatted_time = datetime.datetime.now().strftime("%A %d %B %Y at %H:%M")

    # Extract region from the player's roles
            region_role = next(
                (role.name for role in user.roles if role.name.upper() in ["NA", "EU", "SA", "ASIA", "OCE", "AF"]),
                "Unknown Region"
            )

            log_embed = discord.Embed(
                title="**Player Join Log**",
                description=(
                    f"**Player:** {user.mention} (`{user.display_name}`)\n"
                    f"**IGN:** `{ign}`\n"
                    f"**Region:** `{region_role}`\n"
                    f"**Host:** <@{self.host_id}>\n"
                    f"**Thread:** <#{self.thread_id}>"
                ),
                color=discord.Color.green()
            )

            log_embed.set_footer(
                text=f"Players: {len(game['players'])}/{self.player_cap} • Thread ID: {self.thread_id} • {formatted_time}"
            )

            await log_channel.send(embed=log_embed)

        await interaction.response.send_message("You've joined the league!", ephemeral=True)

    @discord.ui.button(label="Join League", style=discord.ButtonStyle.primary, custom_id="join_league")
    async def join(self, interaction: discord.Interaction, button: discord.ui.Button):
        user = interaction.user

        # Reload user_data fresh from file
        try:
            with open(user_data_file, "r") as f:
                user_data.clear()
                user_data.update(json.load(f))
        except Exception as e:
            print(f"[ERROR] Failed to reload user_data: {e}")

        game = active_games.get(self.host_id)
        if not game or any(player["id"] == user.id for player in game["players"]):
            return await interaction.response.send_message("You are already in the match or the match no longer exists.", ephemeral=True)

        user_entry = user_data.get(str(user.id))
        display_name = user_entry.get("display_name") if user_entry else None

        print(f"[DEBUG] Display name for {user.name} (ID: {user.id}): '{display_name}'")

        if not display_name or not isinstance(display_name, str) or not display_name.strip():
            print(f"[MODAL] Triggering display name modal for {user.name} (ID: {user.id})")
            return await interaction.response.send_modal(LeagueNameModal(self, user))

        await self.add_player(interaction, user, display_name.strip())


class LeagueNameModal(discord.ui.Modal, title="Enter Display Name"):
    display_name = discord.ui.TextInput(
        label="Display Name",
        placeholder="Enter your in-game name",
        max_length=32
    )

    def __init__(self, view: LeagueView, user: discord.Member):
        super().__init__()
        self.view = view
        self.user = user

    async def on_submit(self, interaction: discord.Interaction):
        display_name = self.display_name.value.strip()

        print(f"[SAVE] Saving display name: '{display_name}' for {self.user.name} (ID: {self.user.id})")

        # Save to user_data and persist to file
        user_data[str(self.user.id)] = user_data.get(str(self.user.id), {})
        user_data[str(self.user.id)]["display_name"] = display_name

        try:
            with open(user_data_file, "w") as f:
                json.dump(user_data, f, indent=2)
        except Exception as e:
            print(f"[ERROR] Could not save display name: {e}")
            return await interaction.response.send_message("An error occurred while saving your display name.", ephemeral=True)

        # Continue joining process
        await self.view.add_player(interaction, self.user, display_name)


@bot.tree.command(name="prlhostleague", description="Host a league match.")
@app_commands.choices(
    gametype=[
        app_commands.Choice(name="1v1", value="1s"),
        app_commands.Choice(name="2v2", value="2s"),
        app_commands.Choice(name="3v3", value="3s"),
        app_commands.Choice(name="4v4", value="4s")
    ],
    matchtype=[
        app_commands.Choice(name="Default Loadout", value="DL"),
        app_commands.Choice(name="Custom Loadout", value="CL"),
        app_commands.Choice(name="Rank Format", value="RF")
    ],
    region=[
        app_commands.Choice(name="NA", value="NA"),
        app_commands.Choice(name="EU", value="EU"),
        app_commands.Choice(name="ASIA", value="ASIA"),
        app_commands.Choice(name="OCE", value="OCE")
    ]
)
async def prlhostleague(interaction: discord.Interaction, gametype: str, matchtype: str, region: str, link: str):
    await interaction.response.defer(thinking=False, ephemeral=True)  # Stops the "bot is thinking..." message
    guild = interaction.guild
    host = interaction.user
    category = interaction.channel

    player_caps = {"1s": 2, "2s": 4, "3s": 6, "4s": 8}
    player_cap = player_caps.get(gametype, 8)

    thread = await category.create_thread(
        name=f"League ({gametype}) - ({region}) - ({matchtype}) - {host.name}",
        type=discord.ChannelType.private_thread,
        invitable=False
    )

    await thread.add_user(host)

    # Save game data
    active_games[host.id] = {
        "thread_id": thread.id,
        "gametype": gametype,
        "matchtype": matchtype,
        "region": region,
        "link": link,
        "player_cap": player_cap,
        "players": [{"id": host.id, "display_name": host.display_name or host.name}],
        "start_time": datetime.datetime.now()
    }

    gametype_display = {"1s": "1v1", "2s": "2v2", "3s": "3v3", "4s": "4v4"}.get(gametype, gametype)
    matchtype_display = {"DL": "Default Loadout", "CL": "Custom Loadout", "RF": "Rank Format"}.get(matchtype, matchtype)
    formatted_time = datetime.datetime.now().strftime("%A %d %B %Y at %H:%M")
    # Welcome embed
    welcome_embed = discord.Embed(
        description=(
            f"Welcome {host.mention}\n"
            "Use this thread to coordinate with players.\n"
            "Type `/endleague` to close the match.\n\n"
            f"Game details: **{matchtype_display}** {gametype} - {region}\n"
            f"Join here: {link}"
        ),
        color=discord.Color.green()
    )
    welcome_embed.set_footer(text=f"Players: 1/{player_cap}")
    thread_msg = await thread.send(embed=welcome_embed)

    # Display names
    gametype_display = {"1s": "1v1", "2s": "2v2", "3s": "3v3", "4s": "4v4"}.get(gametype, gametype)
    matchtype_display = {"DL": "Default Loadout", "CL": "Custom Loadout", "RF": "Rank Format"}.get(matchtype, matchtype)
    formatted_time = datetime.datetime.now().strftime("%A %d %B %Y at %H:%M")

    # Styled embed for match-hosting
    styled_embed = discord.Embed(
        title=f"**{matchtype_display} League ({region})**",
        description=(
            f"**Hosted by:** `{host.display_name}`\n"
            f"**Mode:** `{gametype_display}`\n"
            f"**Format:** `{matchtype_display}`"
        ),
        color=discord.Color.blue()
    )
    styled_embed.set_footer(text=formatted_time)

    # Send to match-hosting channel
    match_hosting_channel = guild.get_channel(1354174076998127873)
    if match_hosting_channel:
       leagues_role_id = 1354174067715997954
       await match_hosting_channel.send(
           content=f"<@&{leagues_role_id}>",
          embed=styled_embed,
          view=LeagueView(host.id, thread.id, None, thread_msg.id, gametype, matchtype, region, player_cap),
          allowed_mentions=discord.AllowedMentions(roles=True)
      )

    await interaction.followup.send("Your league Match have been hosted.")
        

    log_channel = guild.get_channel(1357869099958403072)
    if log_channel:
        log_embed = discord.Embed(
            title=f"**{matchtype_display} League Log ({region})**",
            description=(
                f"**Host:** {host.mention}\n"
                f"**Mode:** `{gametype_display}`\n"
                f"**Format:** `{matchtype_display}`\n"
                f"**Thread:** {thread.mention}"
            ),
            color=discord.Color.green()
        )
        log_embed.set_footer(text=f"Thread ID: {thread.id}")
        await log_channel.send(embed=log_embed)


@bot.tree.command(name="add", description="Add a user to the league thread (host only).")
async def add(interaction: discord.Interaction, member: discord.Member):
    """Allows the league host to add a player to the thread."""
    host_id = interaction.user.id
    game_info = active_games.get(host_id)

    if not game_info:
        await interaction.response.send_message("You are not hosting any league match.", ephemeral=True)
        return

    thread = interaction.guild.get_thread(game_info["thread_id"])
    if not thread:
        await interaction.response.send_message("The league has ended or the thread is unavailable.", ephemeral=True)
        return

    if len(game_info["players"]) >= game_info["player_cap"]:
        await interaction.response.send_message("The league is full and cannot accept more players.", ephemeral=True)
        return

    # Check if the member is already in the league
    if any(player["id"] == member.id for player in game_info["players"]):
        await interaction.response.send_message(f"{member.mention} is already in the league!", ephemeral=True)
        return

    # Add the player to the league and update game_info
    game_info["players"].append({"id": member.id, "display_name": member.display_name or member.name})
    await thread.add_user(member)

    # Retrieve the player's roles first
    region_role = None
    for role in member.roles:
        if role.name in ["NA", "EU", "ASIA", "OCE"]:
            region_role = role.name
            break

    rank_role = next((role.name for role in member.roles if role.name in ["Gold", "Platinum", "Diamond", "Unranked"]), "Unranked")

    # Send the player embed with their information in the thread
    player_embed = discord.Embed(
        title="Player Added to League",
        description=f"{member.mention} has joined the league!",
        color=discord.Color.blue()
    )
    player_embed.add_field(name="Region", value=(region_role if region_role else "Not specified"), inline=True)
    player_embed.add_field(name="Rank", value=rank_role, inline=True)
    player_embed.set_footer(text=f"Players: {len(game_info['players'])}/{game_info['player_cap']}")
    await thread.send(embed=player_embed)

    # Update the welcome message to reflect the updated player count
    async for msg in thread.history(limit=100, oldest_first=True):
        if msg.embeds:
            embed = msg.embeds[0]
            if embed.footer and "Players:" in embed.footer.text:
                updated_embed = embed.copy()
                updated_embed.set_footer(text=f"Players: {len(game_info['players'])}/{game_info['player_cap']}")
                await msg.edit(embed=updated_embed)
                break

    log_channel = interaction.guild.get_channel(1357869099958403072)
    if log_channel:
        uid = str(member.id)
        ign = user_data.get(uid, {}).get("display_name", "Unknown IGN")
        formatted_time = datetime.datetime.now().strftime("%A %d %B %Y at %H:%M")

        # Detect player region from roles
        region_role = next(
            (role.name for role in member.roles if role.name.upper() in ["NA", "EU", "ASIA", "OCE",]),
            "Unknown Region"
        )

        log_embed = discord.Embed(
            title="**Player Add Log**",
            description=(
                f"**Player:** {member.mention} (`{member.display_name}`)\n"
                f"**IGN:** `{ign}`\n"
                f"**Region:** `{region_role}`\n"
                f"**Host:** {interaction.user.mention}\n"
                f"**Thread:** {thread.mention}"
            ),
            color=discord.Color.blurple()
        )

        log_embed.set_footer(
            text=f"Players: {len(game_info['players'])}/{game_info['player_cap']} • Thread ID: {thread.id} • {formatted_time}"
        )

        await log_channel.send(embed=log_embed)

    if len(game_info["players"]) == game_info["player_cap"]:
        await thread.send("The League is Now Full!")


@bot.tree.command(name="leave", description="Leave the league and remove yourself from the thread.")
async def leave(interaction: discord.Interaction):
    user = interaction.user
    host_id = None
    game_info = None

    # Find the game the user is in
    for host, game in active_games.items():
        if any(player["id"] == user.id for player in game["players"]):
            host_id = host
            game_info = game
            break

    if not game_info:
        await interaction.response.send_message("You are not part of any active league.", ephemeral=True)
        return

    # Remove player from the game (including the host)
    game_info["players"] = [player for player in game_info["players"] if player["id"] != user.id]

    thread = interaction.guild.get_thread(game_info["thread_id"])
    if thread:
        try:
            await thread.remove_user(user)

            # Update the welcome message
            async for msg in thread.history(limit=10, oldest_first=True):
                if msg.embeds and msg.embeds[0].footer and msg.embeds[0].footer.text.startswith("Players:"):
                    updated_embed = msg.embeds[0]
                    updated_embed.set_footer(text=f"Players: {len(game_info['players'])}/{game_info['player_cap']}")
                    await msg.edit(embed=updated_embed)
                    break
        except Exception as e:
            print(f"[Error removing player from thread] {e}")
            await interaction.response.send_message("An error occurred while removing you from the thread.", ephemeral=True)
            return
    else:
        await interaction.response.send_message("The league thread no longer exists or is inaccessible.", ephemeral=True)
        return

    await interaction.response.send_message(f"{user.mention}, you have left the league.", ephemeral=True)


    log_channel = interaction.guild.get_channel(1357869099958403072)
    if log_channel:
        uid = str(user.id)
        ign = user_data.get(uid, {}).get("display_name", "Unknown IGN")
        formatted_time = datetime.datetime.now().strftime("%A %d %B %Y at %H:%M")

    # Detect region from user's roles
        region_role = next(
            (role.name for role in user.roles if role.name.upper() in ["NA", "EU", "ASIA", "OCE"]),
            "Unknown Region"
        )

        log_embed = discord.Embed(
            title="**Player Leave Log**",
            description=(
                f"**Player:** {user.mention} (`{user.display_name}`)\n"
                f"**IGN:** `{ign}`\n"
                f"**Region:** `{region_role}`\n"
                f"**Host:** <@{host_id}>\n"
                f"**Thread:** {thread.mention if thread else 'N/A'}"
            ),
            color=discord.Color.orange()
        )

        log_embed.set_footer(
            text=f"Players Remaining: {len(game_info['players'])}/{game_info['player_cap']} • Thread ID: {thread.id if thread else 'N/A'} • {formatted_time}"
       )

        await log_channel.send(embed=log_embed)





@bot.tree.command(name="remove", description="Remove a player from the league (host only).")
async def remove(interaction: discord.Interaction, member: discord.Member, reason: Optional[str] = "No reason provided"):
    host_id = interaction.user.id
    game_info = active_games.get(host_id)

    if not game_info:
        await interaction.response.send_message("You are not hosting any league match.", ephemeral=True)
        return

    if not any(player["id"] == member.id for player in game_info["players"]):
        await interaction.response.send_message(f"{member.mention} is not in your league.", ephemeral=True)
        return

    # Remove the player from the game
    game_info["players"] = [player for player in game_info["players"] if player["id"] != member.id]

    # Get the thread for the league
    thread = interaction.guild.get_thread(game_info["thread_id"])
    if thread:
        try:
            await thread.remove_user(member)

            # Update the welcome message with the new player count
            async for msg in thread.history(limit=10, oldest_first=True):
                if msg.embeds and msg.embeds[0].footer and msg.embeds[0].footer.text.startswith("Players:"):
                    updated_embed = msg.embeds[0]
                    updated_embed.set_footer(text=f"Players: {len(game_info['players'])}/{game_info['player_cap']}")
                    try:
                        await msg.edit(embed=updated_embed)
                    except Exception as e:
                        print(f"[Error updating welcome embed] {e}")
                    break
        except Exception as e:
            print(f"[Error removing player from thread] {e}")
            await interaction.response.send_message("An error occurred while removing the player from the thread.", ephemeral=True)
            return
    else:
        await interaction.response.send_message("The league thread no longer exists or is inaccessible.", ephemeral=True)
        return



    log_channel = interaction.guild.get_channel(1357869099958403072)
    if log_channel:
        uid = str(member.id)
        ign = user_data.get(uid, {}).get("display_name", "Unknown IGN")
        formatted_time = datetime.datetime.now().strftime("%A %d %B %Y at %H:%M")

    # Detect region from user's roles
        region_role = next(
            (role.name for role in member.roles if role.name.upper() in ["NA", "EU", "ASIA", "OCE"]),
            "Unknown Region"
        )

        log_embed = discord.Embed(
            title="**Player Removed from League**",
            description=(
                f"**Removed Player:** {member.mention} (`{member.display_name}`)\n"
                f"**IGN:** `{ign}`\n"
                f"**Region:** `{region_role}`\n"
                f"**Host:** {interaction.user.mention}\n"
                f"**Thread:** {thread.mention if thread else 'N/A'}"
                f"**Reason:** {reason}"
            ),
            color=discord.Color.red()
        )

        log_embed.set_footer(
            text=f"Players Remaining: {len(game_info['players'])}/{game_info['player_cap']} • Thread ID: {thread.id if thread else 'N/A'} • {formatted_time}"
        )

        await log_channel.send(embed=log_embed)

    # Confirm removal to the host
    await interaction.response.send_message(f"{member.mention} has been removed from the league.", ephemeral=True)




@bot.tree.command(name="endleague", description="Ends your league and locks the thread.")
async def endleague(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)  # <- Responds immediately to avoid timeout

    host_id = interaction.user.id
    game_info = active_games.get(host_id)

    if not game_info:
        await interaction.followup.send("You are not hosting any active league.")
        return

    thread = interaction.guild.get_thread(game_info["thread_id"])

    # Lock and archive the thread
    if thread:
        try:
            await thread.edit(locked=True, archived=True, reason="League ended by host via /endleague")
        except Exception as e:
            print(f"[Error locking thread] {e}")
            await interaction.followup.send("Failed to lock the thread. Please check permissions.")
            return

    # Clean up the game data
    active_games.pop(host_id, None)

    await interaction.followup.send("Your league has been ended and the thread locked.")

    # Log the event in the log channe

    log_channel = interaction.guild.get_channel(1357869099958403072)
    if log_channel:
        formatted_time = datetime.datetime.now().strftime("%A %d %B %Y at %H:%M")

        log_embed = discord.Embed(
            title="**League Ended**",
            description=f"{interaction.user.mention} ended the league.",
            color=discord.Color.red(),
            timestamp=datetime.datetime.utcnow()
        )
        log_embed.add_field(name="Host", value=interaction.user.mention, inline=False)
        log_embed.add_field(name="Thread", value=thread.mention if thread else "Thread not found", inline=True)
        log_embed.set_footer(text=f"Ended at: {formatted_time} | Thread ID: {thread.id if thread else 'N/A'}")

        await log_channel.send(embed=log_embed)


# ——— Persistence boilerplate ———
user_data_file = "user_data_prl.json"
try:
    with open(user_data_file, "r") as f:
        user_data = json.load(f)
except FileNotFoundError:
    user_data = {}

active_strikes = user_data.get("strikes", {})

def save_user_data(data):
    with open(user_data_file, "w") as f:
        json.dump(data, f, indent=2)

def save_strike_data():
    user_data["strikes"] = active_strikes
    save_user_data(user_data)

# ——— /strike ———
@bot.tree.command(name="strike", description="Add a strike to a player.")
@app_commands.choices(
    striketype=[
        app_commands.Choice(name="Host", value="host"),
        app_commands.Choice(name="Grief", value="grief")
    ]
)
async def strike(interaction: discord.Interaction, user: discord.Member, striketype: str, reason: str):
    await interaction.response.defer(thinking=False, ephemeral=True)
    guild = interaction.guild

    # Get or init user data
    player_data = active_strikes.get(str(user.id), {"host": 0, "grief": 0})

    # Strike cap check
    if player_data[striketype] >= 3:
        await interaction.followup.send(
            f"**Error:** {user.mention} already has 3 `{striketype}` strikes. You cannot add more.",
            ephemeral=True
        )
        return

    # Add strike
    player_data[striketype] += 1
    active_strikes[str(user.id)] = player_data
    save_strike_data()

    role_assigned = None
    if player_data["host"] >= 3:
        r = discord.utils.get(guild.roles, name="Host Back Ban")
        if r and r not in user.roles:
            await user.add_roles(r)
            role_assigned = r.name

    if player_data["grief"] >= 3:
        r = discord.utils.get(guild.roles, name="Griefing Bail")
        if r and r not in user.roles:
            await user.add_roles(r)
            role_assigned = r.name

    await interaction.followup.send("Strike added successfully.", ephemeral=True)

    # Log channel embed
    log_channel = guild.get_channel(1357869099958403072)
    if log_channel:
        embed = discord.Embed(
            title="**Strike Added**",
            description=f"A **{striketype}** strike has been added to {user.mention} by {interaction.user.mention}.",
            color=discord.Color.red(),
        )
        embed.add_field(name="Strike Type", value=striketype.capitalize(), inline=False)
        embed.add_field(name="Reason", value=reason, inline=False)
        embed.add_field(name="Host Strikes", value=player_data["host"], inline=True)
        embed.add_field(name="Grief Strikes", value=player_data["grief"], inline=True)
        if role_assigned:
            embed.add_field(name="Role Assigned", value=role_assigned, inline=False)

        await log_channel.send(embed=embed)

    # Strikes channel embed
    strikes_channel = discord.utils.get(guild.text_channels, name="host-strikes")
    if strikes_channel:
        embed = discord.Embed(
            title="Strike Notification",
            description=f"A **{striketype}** strike has been added to {user.mention}.",
            color=discord.Color.red(),
        )
        embed.add_field(name="Reason", value=reason, inline=False)
        embed.add_field(name="Host Strikes", value=player_data["host"], inline=True)
        embed.add_field(name="Grief Strikes", value=player_data["grief"], inline=True)

        await strikes_channel.send(embed=embed)


# ——— /strikeremove ———
@bot.tree.command(name="strikeremove", description="Remove a strike from a player.")
@app_commands.choices(
    striketype=[
        app_commands.Choice(name="Host", value="host"),
        app_commands.Choice(name="Grief", value="grief")
    ]
)
async def strikeremove(interaction: discord.Interaction, user: discord.Member, striketype: str, reason: str):
    await interaction.response.defer(thinking=False, ephemeral=True)
    guild = interaction.guild
    user_id = str(user.id)

    # Get or initialize the player's strike data
    player_data = active_strikes.get(user_id, {"host": 0, "grief": 0})

    # Error if the user doesn't have a strike of that type
    if player_data.get(striketype, 0) <= 0:
        await interaction.followup.send(
            f"{user.mention} has no **{striketype}** strikes to remove.",
            ephemeral=True
        )
        return

    # Remove a strike
    player_data[striketype] -= 1
    active_strikes[user_id] = player_data
    save_strike_data()

    # Remove associated role if below threshold
    role_removed = None
    if striketype == "host" and player_data["host"] < 3:
        role = discord.utils.get(guild.roles, name="Host Back Ban")
        if role and role in user.roles:
            await user.remove_roles(role)
            role_removed = role.name

    elif striketype == "grief" and player_data["grief"] < 3:
        role = discord.utils.get(guild.roles, name="Griefing Bail")
        if role and role in user.roles:
            await user.remove_roles(role)
            role_removed = role.name

    # Confirm to command user
    await interaction.followup.send("Strike successfully removed.", ephemeral=True)

    # Log to #strike-logs channel
    log_channel = guild.get_channel(1357869099958403072)
    if log_channel:
        embed = discord.Embed(
            title="**Strike Removed**",
            description=f"A **{striketype}** strike has been removed from {user.mention} by {interaction.user.mention}.",
            color=discord.Color.green()
        )
        embed.add_field(name="Strike Type", value=striketype.capitalize(), inline=False)
        embed.add_field(name="Reason", value=reason, inline=False)
        embed.add_field(name="Total Host Strikes", value=player_data["host"], inline=True)
        embed.add_field(name="Total Grief Strikes", value=player_data["grief"], inline=True)
        if role_removed:
            embed.add_field(name="Role Removed", value=role_removed, inline=False)

        await log_channel.send(embed=embed)

    # Send notification to public channel
    strikes_channel = discord.utils.get(guild.text_channels, name="host-strikes")
    if strikes_channel:
        embed = discord.Embed(
            title="Strike Removal Notification",
            description=f"A **{striketype}** strike has been removed from {user.mention}.",
            color=discord.Color.green()
        )
        embed.add_field(name="Reason", value=reason, inline=False)
        embed.add_field(name="Host Strikes", value=player_data["host"], inline=True)
        embed.add_field(name="Grief Strikes", value=player_data["grief"], inline=True)

        await strikes_channel.send(embed=embed)


# ——— /strikecheck ———
@bot.tree.command(name="strikecheck", description="Check the strike history of a player.")
async def strikecheck(interaction: discord.Interaction, user: discord.Member):

    guild = interaction.guild
    player_data = active_strikes.get(str(user.id), {"host": 0, "grief": 0})

    
    embed = discord.Embed(
        title=f"Strike History for {user.name}",
        description=f"Strike data for {user.mention}:",
        color=discord.Color.blue(),
        
    )
    embed.add_field(name="Host Strikes",      value=player_data["host"], inline=True)
    embed.add_field(name="Grief Strikes",     value=player_data["grief"],inline=True)
    embed.add_field(name="Host Back Ban Role",value="Yes" if discord.utils.get(guild.roles, name="Host Back Ban") in user.roles else "No", inline=True)
    embed.add_field(name="Griefing Bail Role",value="Yes" if discord.utils.get(guild.roles, name="Griefing Bail") in user.roles else "No", inline=True)

    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="displayset", description="Set your in-game display name")
@app_commands.describe(name="Your display name")
async def displayset(interaction: discord.Interaction, name: str):
    user_data[str(interaction.user.id)] = user_data.get(str(interaction.user.id), {})
    user_data[str(interaction.user.id)]["display_name"] = name.strip()

    try:
        with open(user_data_file, "w") as f:
            json.dump(user_data, f, indent=2)
    except Exception as e:
        print(f"[ERROR] Could not save display name: {e}")
        return await interaction.response.send_message("Failed to save your display name.", ephemeral=True)

    await interaction.response.send_message(f"Your display name has been set to `{name}`.", ephemeral=True)


from typing import Optional

@bot.tree.command(name="showdisplay", description="Show a user's current in-game name.")
@app_commands.describe(user="The user whose in-game name you want to check (defaults to yourself)")
async def showdisplay(interaction: discord.Interaction, user: Optional[discord.Member] = None):
    # If no user is provided, default to the user who invoked the command.
    user = user or interaction.user
    uid = str(user.id)

    # Retrieve the in-game name from user_data; using "display_name" key
    in_game_name = user_data.get(uid, {}).get("display_name")

    if in_game_name and in_game_name.strip():
        response_message = f"{user.mention}'s in-game name is: **{in_game_name}**"
    else:
        response_message = f"{user.mention} has not set an in-game name yet."

    await interaction.response.send_message(response_message, ephemeral=True)

@bot.tree.command(name="topplayers", description="Manually update the Top Players leaderboard.")
async def topplayers(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    # Update leaderboard and expect a return (e.g., True if updated, False otherwise)
    updated = await update_leaderboard(interaction.guild)

    if updated:
        await interaction.followup.send("Top players leaderboard updated.", ephemeral=True)
    else:
        await interaction.followup.send("Leaderboard is already up-to-date. No changes made.", ephemeral=True)
@bot.tree.command(name="help", description="View a list of PRL bot commands.")
async def help_command(interaction: discord.Interaction):
    embed = discord.Embed(
        title="PRL Bot Commands",
        description="Here’s a list of available PRL commands, grouped by purpose.",
        color=discord.Color.blurple()
    )

    # Hosting Commands
    embed.add_field(
        name="**League Hosting**",
        value=(
            "`/prlhostleague` - Host a PRL league match.\n"
            "`/add` - Manually add a player to a league match.\n"
            "`/leave` - Leave the currently joined match.\n"
            "`/remove` - Remove a player from the match.\n"
            "`/endleague` - End an active league match."
        ),
        inline=False
    )

    # Strike System
    embed.add_field(
        name="**Strike System**",
        value=(
            "`/strike` - Issue a strike to a user.\n"
            "`/strikeremove` - Remove a strike from a user.\n"
            "`/strikecheck` - View a user's current strikes."
        ),
        inline=False
    )

    # Display Name System
    embed.add_field(
        name="**Display Name**",
        value=(
            "`/displayset` - Set or change your display name.\n"
            "`/showdisplay` - Show your current display name."
        ),
        inline=False
    )

    # Misc
    embed.add_field(
        name="**Other**",
        value=(
            "`/topplayers` - View top-ranked players.\n"
            "`/about` - Information about the PRL BOT."
        ),
        inline=False
    )

    embed.set_footer(text="Need help? Contact a league admin or mod.")
    await interaction.response.send_message(embed=embed, ephemeral=True)


# Constants and mappings
RANK_NAMES = {
    "r1": "R1 - Drone",
    "r2": "R2 - Bot",
    "r3": "R3 - Noob",
    "r4": "R4 - Semi-Pro",
    "r5": "R5 - Pro",
    "r6": "R6 - Ancient",
    "r7": "R7 - Mythical",
    "r8": "R8 - Master",
    "r9": "R9 - Supreme",
    "r10": "R10 - Overlord",
    "r11": "R11 - Celestial"
}
# Defines the hierarchy from highest (r11) to lowest (r1)
RANK_ORDER = list(RANK_NAMES.keys())[::-1]

TIER_NAMES = ["low", "mid", "high"]
USER_DATA_FILE = "user_data_prl.json"

# JSON load/save helpers
def load_user_data():
    if not os.path.exists(USER_DATA_FILE):
        return {}
    with open(USER_DATA_FILE, "r") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return {}


def save_user_data(data):
    with open(USER_DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)

# Helper for transient error messages
def send_error(channel: discord.TextChannel, content: str):
    return channel.send(content, delete_after=4)

# Bot event
@bot.event
async def on_message(message: discord.Message):
    if not message.guild or message.author.bot:
        return

    if message.channel.name.lower() != "rank-logs":
        return

    if not message.mentions or " to " not in message.content.lower():
        return

    user = message.mentions[0]
    content = message.content.lower()

    try:
        old_text, new_text = content.split(" to ", 1)
        old_parts = old_text.split()[-2:]
        new_parts = new_text.split()[:2]

        old_rank = old_parts[0] if old_parts and old_parts[0] in RANK_NAMES else "n/a"
        old_tier = old_parts[1] if len(old_parts) > 1 and old_parts[1] in TIER_NAMES else None

        new_rank = new_parts[0] if new_parts and new_parts[0] in RANK_NAMES else "n/a"
        new_tier = new_parts[1] if len(new_parts) > 1 and new_parts[1] in TIER_NAMES else None
    except Exception:
        await send_error(
            message.channel,
            "**Error parsing rank change.** Use `@user r7 low to r8 high`"
        )
        return

    old_rank_role = discord.utils.get(message.guild.roles, name=RANK_NAMES.get(old_rank))
    old_tier_role = discord.utils.get(
        message.guild.roles,
        name=old_tier.capitalize() if old_tier else None
    )
    new_rank_role = discord.utils.get(message.guild.roles, name=RANK_NAMES.get(new_rank))
    new_tier_role = discord.utils.get(
        message.guild.roles,
        name=new_tier.capitalize() if new_tier else None
    )

    if old_rank != "n/a" and (not old_rank_role or old_rank_role not in user.roles):
        await send_error(
            message.channel,
            f"**Error:** {user.mention} does not have rank `{RANK_NAMES.get(old_rank, old_rank)}`."
        )
        return

    if old_tier and (not old_tier_role or old_tier_role not in user.roles):
        await send_error(
            message.channel,
            f"**Error:** {user.mention} does not have tier `{old_tier.capitalize()}`."
        )
        return

    if new_rank != "n/a" and not new_rank_role:
        await send_error(
            message.channel,
            f"**Error:** Invalid new rank `{new_rank}`."
        )
        return

    if new_tier and not new_tier_role:
        await send_error(
            message.channel,
            f"**Error:** Invalid new tier `{new_tier}`."
        )
        return

    roles_to_remove = []
    if old_rank_role and old_rank_role in user.roles:
        roles_to_remove.append(old_rank_role)
    if old_tier_role and old_tier_role in user.roles:
        roles_to_remove.append(old_tier_role)

    if roles_to_remove:
        await user.remove_roles(*roles_to_remove)

    roles_to_add = []
    if new_rank != "n/a" and new_rank_role and new_rank_role not in user.roles:
        roles_to_add.append(new_rank_role)
    if new_tier and new_tier_role and new_tier_role not in user.roles:
        roles_to_add.append(new_tier_role)

    if roles_to_add:
        await user.add_roles(*roles_to_add)

    # Save to JSON
    data = load_user_data()
    data[str(user.id)] = {
        "rank": new_rank if new_rank in RANK_NAMES else "n/a",
        "tier": new_tier if new_tier in TIER_NAMES else "n/a"
    }
    save_user_data(data)

    await message.channel.send(
        f"Updated {user.mention}: rank → `{new_rank}` | tier → `{new_tier or 'n/a'}`",
        delete_after=4
    )

    log_channel = message.guild.get_channel(1357869099958403072)
    if log_channel:
        prev = RANK_NAMES.get(old_rank, old_rank.upper() if old_rank != "n/a" else "N/A")
        if old_tier:
            prev += f" {old_tier.capitalize()}"
        newv = RANK_NAMES.get(new_rank, new_rank.upper() if new_rank != "n/a" else "N/A")
        if new_tier:
            newv += f" {new_tier.capitalize()}"

        embed = discord.Embed(
            title="Rank Change Logged",
            color=discord.Color.purple(),
            timestamp=datetime.utcnow()
        )
        embed.add_field(name="User", value=user.mention, inline=True)
        embed.add_field(name="Previous", value=prev, inline=True)
        embed.add_field(name="New", value=newv, inline=True)
        embed.set_footer(text=f"User ID: {user.id}")
        await log_channel.send(embed=embed)

    top5 = set(RANK_ORDER[:5])
    was_top5 = old_rank in top5
    now_top5 = new_rank in top5
    if was_top5 != now_top5 or (was_top5 and old_rank != new_rank):
        await update_leaderboard(message.guild)


async def update_leaderboard(guild: discord.Guild):
    leaderboard_channel = discord.utils.get(guild.text_channels, name="top-players")
    if not leaderboard_channel:
        return

    top_players = []
    for member in guild.members:
        for code in RANK_ORDER[:5]:
            role = discord.utils.get(guild.roles, name=RANK_NAMES[code])
            if role and role in member.roles:
                tier_role = next((r for r in member.roles if r.name.lower() in TIER_NAMES), None)
                tier_str = tier_role.name if tier_role else "Unranked"
                top_players.append((member.display_name, RANK_NAMES[code], tier_str))
                break

    if not top_players:
        embed = discord.Embed(
            title="Top Players Leaderboard",
            description="No top players yet.",
            color=discord.Color.gold()
        )
    else:
        top_players.sort(key=lambda p: (RANK_ORDER.index(list(RANK_NAMES.keys())[list(RANK_NAMES.values()).index(p[1])]), p[0].lower()))
        embed = discord.Embed(
            title="**WELCOME TO THE RANKED RING**",
            description="═══════════════════════════════\n        **CHAMPIONS STAND TALL**\n═══════════════════════════════\n\n",
            color=discord.Color.dark_gold()
        )
        medals = ["🥇", "🥈", "🥉"]
        for i, (name, rank, tier) in enumerate(top_players):
            medal = medals[i] if i < 3 else f"#{i+1}"
            embed.description += f"{medal} **{name}**\n        └— Rank: `{rank} {tier}`\n\n"
        embed.description += "═══════════════════════════════"

    embed.set_footer(text=f"Last Updated • {datetime.now().strftime('%B %d, %Y')}")

    pins = await leaderboard_channel.pins()
    for msg in pins:
        if msg.author == guild.me and msg.embeds:
            await msg.edit(embed=embed)
            return
    msg = await leaderboard_channel.send(embed=embed)
    await msg.pin()
import time
start_time = time.time()

def get_uptime():
    seconds = int(time.time() - start_time)
    days, seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)
    return f"{days}d {hours}h {minutes}m"


@bot.tree.command(name="about", description="Information about the PRL BOT.")
async def about(interaction: discord.Interaction):
    owner_id = 1321987310585249872
    owner_mention = f"<@{owner_id}>"

    embed = discord.Embed(
        title="**About PRL BOT**",
        description="A competitive league management bot built for organizing matches, tracking player ranks, and managing infractions with ease.",
        color=discord.Color.blurple()
    )

    embed.add_field(name="Developer", value=owner_mention, inline=True)
    embed.add_field(name="Key Features", value="• Match Hosting\n• Rank Tracking\n• Strike System", inline=True)
    embed.set_footer(text=f"Uptime: {get_uptime()} • PRL BOT")

    await interaction.response.send_message(embed=embed, ephemeral=True)




@bot.event
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    try:
        # Known error: Missing permissions
        if isinstance(error, app_commands.CheckFailure):
            await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)

        # Known error: Error occurred while executing command
        elif isinstance(error, app_commands.CommandInvokeError):
            print(f"[CommandInvokeError] {error.original}")
            if interaction.response.is_done():
                await interaction.followup.send("An error occurred while executing the command. Please try again later.", ephemeral=True)
            else:
                await interaction.response.send_message("An error occurred while executing the command. Please try again later.", ephemeral=True)

        # Fallback for unexpected errors
        else:
            print(f"[AppCommandError] {error}")
            if interaction.response.is_done():
                await interaction.followup.send("An unexpected error occurred. Please try again later.", ephemeral=True)
            else:
                await interaction.response.send_message("An unexpected error occurred. Please try again later.", ephemeral=True)

    except Exception as e:
        print(f"[Error Handler Failed] {e}")


@bot.event
async def on_ready():
    try:
        synced = await bot.tree.sync()
        print(f"🌍 Globally synced {len(synced)} commands.")
    except Exception as e:
        print(f"❌ Sync failed: {e}")



bot.run(TOKEN)
