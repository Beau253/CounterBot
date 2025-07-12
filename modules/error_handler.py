# /modules/error_handler.py

import os
import traceback
import logging
import discord

log = logging.getLogger(__name__)
BOT_MODE = os.getenv('BOT_MODE', 'development')

async def send_error_report(interaction: discord.Interaction, error: Exception):
    """
    Handles errors by sending a detailed report in dev mode, or a generic
    message in production mode.
    """
    # Log the full error to the console, using the correct interaction properties
    log.error(f"Error occurred in command '{interaction.command.name}': {error}", exc_info=True)

    # --- Production Mode: Send a generic, user-friendly message ---
    if BOT_MODE == 'production':
        message = "Sorry, an unexpected error occurred. The developers have been automatically notified."
        try:
            # Check if we have already responded (e.g., with defer())
            if interaction.response.is_done():
                await interaction.followup.send(message, ephemeral=True)
            else:
                # If not, send the initial response
                await interaction.response.send_message(message, ephemeral=True)
        except discord.errors.NotFound:
            log.warning("Could not send production error message: interaction expired.")
        except Exception as e:
            log.error(f"Failed to send production error message to Discord: {e}", exc_info=True)
        return

    # --- Development Mode: Send a detailed, embedded traceback ---
    try:
        error_title = f"💥 Crash Report in: `/{interaction.command.name}`"
        error_description = (
            "An unhandled exception was caught by the error handler."
        )

        error_traceback = "".join(traceback.format_exception(type(error), error, error.__traceback__))

        traceback_limit = 1024
        if len(error_traceback) > traceback_limit:
            formatted_traceback = f"```{error_traceback[:traceback_limit - 20]}... (truncated)```"
        else:
            formatted_traceback = f"```{error_traceback}```"

        embed = discord.Embed(
            title=error_title,
            description=error_description,
            color=discord.Color.red()
        )
        embed.add_field(name="Traceback", value=formatted_traceback, inline=False)
        embed.set_footer(text="This is a development-only error report.")

        if interaction.response.is_done():
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message(embed=embed, ephemeral=True)

    except Exception as e:
        log.critical(f"CRITICAL: Failed to send dev error report to Discord: {e}", exc_info=True)
        try:
            await interaction.followup.send(f"**Failed to generate full error report.**\n**Original Error:**\n```\n{error}\n```", ephemeral=True)
        except Exception:
            pass