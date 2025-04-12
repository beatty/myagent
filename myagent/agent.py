import datetime
import yaml
import os
import json
import base64
import subprocess
import threading
import shlex
from pathlib import Path
from zoneinfo import ZoneInfo
from google.adk.agents import Agent
import google.genai.types as types


def load_config() -> dict:
    """Load the agent configuration from YAML file.

    Returns:
        dict: The agent configuration.
    """
    config_path = os.path.join(os.path.dirname(__file__), "config.yaml")
    if os.path.exists(config_path):
        with open(config_path, "r") as f:
            return yaml.safe_load(f)
    return {}


def get_bio() -> dict:
    """Retrieves information about the owner.

    Returns:
        dict: the bio of the owner.
    """
    config = load_config()
    owner = config.get("owner", {})

    return {
        "status": "success",
        "name": owner.get("name", "Unknown"),
        "email": owner.get("email", ""),
        "bio": owner.get("bio", ""),
    }

def relay_message(user_email: str, priority: str, message: str) -> dict:
    """Relay's a message from the user to the owner.
    Saves the message to a file in ~/.myagent directory.

    Args:
        user_email: The email of the user sending the message
        priority: The priority of the message
        message: The content of the message

    Returns:
        dict: information about if and how the message is being delivered
    """
    try:
        config = load_config()
        owner = config.get("owner", {})

        # Create ~/.myagent directory if it doesn't exist
        myagent_dir = Path.home() / ".myagent"
        myagent_dir.mkdir(exist_ok=True)

        # Create a timestamp for the message
        timestamp = datetime.datetime.now().isoformat()

        # Create a filename with timestamp
        filename = f"message_{timestamp.replace(':', '-').replace('.', '_')}.json"
        file_path = myagent_dir / filename

        # Prepare message data
        message_data = {
            "timestamp": timestamp,
            "user_email": user_email,
            "priority": priority,
            "message": message,
            "owner": owner.get("name", "Unknown")
        }

        # Write message to file
        with open(file_path, "w") as f:
            json.dump(message_data, f, indent=2)

        return {
            "status": "success",
            "disposition": f"The message was saved to {file_path} and will be relayed to the owner",
        }
    except Exception as e:
        # Log the error but don't expose internal details to the user
        print(f"Error in relay_message: {e}")
        return {
            "status": "error",
            "disposition": "There was an error relaying your message. Please try again later.",
        }

def request_meeting(topic: str, date_time: str) -> dict:
    """Requests a meeting with the owner.

    Returns:
        dict: information about the status of the meeting the user is requesting.
    """
    config = load_config()
    owner = config.get("owner", {})

    return {
        "status": "success",
        "disposition": "I've sent the meeting request to the owner.",
    }

def write_file(filename: str, content: str, tool_context=None) -> dict:
    """Writes content to a file and optionally saves it as an artifact.
    If no path is specified in the filename, defaults to ~/wall directory.

    Args:
        filename: The name of the file to write to
        content: The content to write to the file
        tool_context: The ToolContext object provided by the ADK

    Returns:
        dict: information about the status of the file writing operation
    """
    try:
        # First write to the filesystem
        result = write_file_to_filesystem(filename, content)

        # If we have a tool_context, also save as an artifact
        if tool_context is not None and result["status"] == "success":
            try:
                # Determine MIME type based on file extension
                mime_type = "text/plain"  # Default MIME type
                if filename.lower().endswith((".jpg", ".jpeg")):
                    mime_type = "image/jpeg"
                elif filename.lower().endswith(".png"):
                    mime_type = "image/png"
                elif filename.lower().endswith(".pdf"):
                    mime_type = "application/pdf"
                elif filename.lower().endswith(".json"):
                    mime_type = "application/json"

                # Create a Part object from the content
                content_bytes = content.encode('utf-8')
                artifact = types.Part.from_data(data=content_bytes, mime_type=mime_type)

                # Save the artifact
                version = tool_context.save_artifact(filename=filename, artifact=artifact)

                # Add artifact info to the result
                result["artifact_saved"] = True
                result["artifact_version"] = version
                result["disposition"] += f" and saved as artifact '{filename}' (version {version})"

            except ValueError as e:
                # This happens if artifact_service is not configured
                print(f"Artifact service not available: {e}")
                # We still return success since the file was written to the filesystem
                result["artifact_saved"] = False
                result["artifact_error"] = str(e)
            except Exception as e:
                # Log the error but don't fail the operation since the file was written
                print(f"Error saving artifact: {e}")
                result["artifact_saved"] = False
                result["artifact_error"] = str(e)

        return result
    except Exception as e:
        # Log the error and relay it back to the LLM
        error_message = f"Error in write_file: {e}"
        print(error_message)
        return {
            "status": "error",
            "disposition": f"There was an error writing to the file: {str(e)}",
            "error": str(e)
        }

def write_file_to_filesystem(filename: str, content: str) -> dict:
    """Writes content to a file in the filesystem.
    If no path is specified in the filename, defaults to ~/wall directory.

    Args:
        filename: The name of the file to write to
        content: The content to write to the file

    Returns:
        dict: information about the status of the file writing operation
    """
    try:
        # Determine the file path
        file_path = Path(filename)

        # If no directory specified, use ~/wall as default
        if not file_path.is_absolute() and '/' not in filename:
            # Create ~/wall directory if it doesn't exist
            wall_dir = Path.home() / "wall"
            wall_dir.mkdir(exist_ok=True)
            file_path = wall_dir / filename

        # Create parent directories if they don't exist
        file_path.parent.mkdir(parents=True, exist_ok=True)

        # Write content to file
        with open(file_path, "w") as f:
            f.write(content)

        return {
            "status": "success",
            "disposition": f"Content was successfully written to {file_path}",
            "file_path": str(file_path)
        }
    except Exception as e:
        # Log the error and relay it back to the LLM
        error_message = f"Error in write_file_to_filesystem: {e}"
        print(error_message)
        return {
            "status": "error",
            "disposition": f"There was an error writing to the file: {str(e)}",
            "error": str(e)
        }

def read_file(filename: str, tool_context=None) -> dict:
    """Reads content from a file using the ADK artifacts system.
    If no path is specified in the filename, defaults to ~/wall directory.

    Args:
        filename: The name of the file to read from
        tool_context: The ToolContext object provided by the ADK

    Returns:
        dict: information about the status of the file reading operation and the content
    """
    try:
        # Check if we have a tool_context for using artifacts
        if tool_context is None:
            # Fall back to file system if no tool_context is provided
            return read_file_from_filesystem(filename)

        try:
            # Try to load the artifact using the ADK artifacts system
            artifact = tool_context.load_artifact(filename)

            if artifact is None:
                # If artifact not found, try with user: prefix
                if not filename.startswith("user:"):
                    artifact = tool_context.load_artifact(f"user:{filename}")

                # If still not found, try filesystem fallback
                if artifact is None:
                    return read_file_from_filesystem(filename)

            # Extract data from the artifact
            if not hasattr(artifact, 'inline_data') or artifact.inline_data is None:
                return {
                    "status": "error",
                    "disposition": f"Artifact found but contains no data: {filename}",
                    "error": "No data in artifact"
                }

            mime_type = artifact.inline_data.mime_type
            data = artifact.inline_data.data  # This is bytes

            # For binary files, encode as base64
            if mime_type.startswith("image/") or mime_type == "application/pdf":
                base64_data = base64.b64encode(data).decode('ascii')
                return {
                    "status": "success",
                    "disposition": f"Content was successfully read from artifact {filename}",
                    "artifact_name": filename,
                    "mime_type": mime_type,
                    "encoding": "base64",
                    "data": base64_data
                }

            # For text files, decode to string
            else:
                try:
                    content = data.decode('utf-8')
                    return {
                        "status": "success",
                        "disposition": f"Content was successfully read from artifact {filename}",
                        "artifact_name": filename,
                        "mime_type": mime_type,
                        "content": content
                    }
                except UnicodeDecodeError:
                    # If we can't decode as text, fall back to binary/base64
                    base64_data = base64.b64encode(data).decode('ascii')
                    return {
                        "status": "success",
                        "disposition": f"Content was successfully read from artifact {filename} (binary)",
                        "artifact_name": filename,
                        "mime_type": mime_type,
                        "encoding": "base64",
                        "data": base64_data
                    }

        except ValueError as e:
            # This happens if artifact_service is not configured
            print(f"Artifact service not available: {e}")
            return read_file_from_filesystem(filename)

    except Exception as e:
        # Log the error and relay it back to the LLM
        error_message = f"Error in read_file: {e}"
        print(error_message)
        return {
            "status": "error",
            "disposition": f"There was an error reading from the file: {str(e)}",
            "error": str(e)
        }

def list_artifacts(tool_context) -> dict:
    """Lists all available artifacts for the user.

    Args:
        tool_context: The ToolContext object provided by the ADK

    Returns:
        dict: information about the available artifacts
    """
    try:
        if tool_context is None:
            return {
                "status": "error",
                "disposition": "Cannot list artifacts: tool_context is not available",
                "error": "No tool_context provided"
            }

        try:
            # Get the list of artifacts from the tool_context
            artifacts = tool_context.list_artifacts()

            # Also list files in the ~/wall directory for completeness
            wall_dir = Path.home() / "wall"
            filesystem_files = []
            if wall_dir.exists() and wall_dir.is_dir():
                filesystem_files = [f.name for f in wall_dir.iterdir() if f.is_file()]

            # Combine both lists and remove duplicates
            all_files = list(set(artifacts + filesystem_files)) if artifacts else filesystem_files.copy()
            all_files.sort()  # Sort alphabetically

            return {
                "status": "success",
                "disposition": f"Found {len(all_files)} files",
                "artifacts": artifacts,
                "filesystem_files": filesystem_files,
                "all_files": all_files
            }

        except ValueError as e:
            # This happens if artifact_service is not configured
            print(f"Artifact service not available: {e}")

            # Fall back to just listing files in the ~/wall directory
            wall_dir = Path.home() / "wall"
            filesystem_files = []
            if wall_dir.exists() and wall_dir.is_dir():
                filesystem_files = [f.name for f in wall_dir.iterdir() if f.is_file()]

            return {
                "status": "partial",
                "disposition": f"Artifact service not available. Found {len(filesystem_files)} files in filesystem.",
                "error": str(e),
                "filesystem_files": filesystem_files,
                "all_files": filesystem_files
            }

    except Exception as e:
        # Log the error and relay it back to the LLM
        error_message = f"Error in list_artifacts: {e}"
        print(error_message)
        return {
            "status": "error",
            "disposition": f"There was an error listing artifacts: {str(e)}",
            "error": str(e)
        }

def read_file_from_filesystem(filename: str) -> dict:
    """Reads content from a file in the filesystem.
    If no path is specified in the filename, defaults to ~/wall directory.

    Args:
        filename: The name of the file to read from

    Returns:
        dict: information about the status of the file reading operation and the content
    """
    try:
        # Determine the file path
        file_path = Path(filename)

        # If no directory specified, use ~/wall as default
        if not file_path.is_absolute() and '/' not in filename:
            wall_dir = Path.home() / "wall"
            file_path = wall_dir / filename

        # Check if file exists
        if not file_path.exists():
            return {
                "status": "error",
                "disposition": f"File not found: {file_path}",
                "error": "File not found"
            }

        # Determine MIME type based on file extension
        mime_type = "text/plain"  # Default MIME type
        if file_path.suffix.lower() in [".jpg", ".jpeg"]:
            mime_type = "image/jpeg"
        elif file_path.suffix.lower() == ".png":
            mime_type = "image/png"
        elif file_path.suffix.lower() == ".pdf":
            mime_type = "application/pdf"
        elif file_path.suffix.lower() == ".json":
            mime_type = "application/json"

        # For binary files, read as binary and encode as base64
        if mime_type.startswith("image/") or mime_type == "application/pdf":
            with open(file_path, "rb") as f:
                file_bytes = f.read()
                # Convert binary data to base64 for safe transport
                base64_data = base64.b64encode(file_bytes).decode('ascii')

                return {
                    "status": "success",
                    "disposition": f"Content was successfully read from {file_path}",
                    "file_path": str(file_path),
                    "mime_type": mime_type,
                    "encoding": "base64",
                    "data": base64_data
                }

        # For text files, read as text
        else:
            try:
                with open(file_path, "r") as f:
                    content = f.read()

                return {
                    "status": "success",
                    "disposition": f"Content was successfully read from {file_path}",
                    "file_path": str(file_path),
                    "mime_type": mime_type,
                    "content": content
                }
            except UnicodeDecodeError:
                # If we can't decode as text, fall back to binary/base64
                with open(file_path, "rb") as f:
                    file_bytes = f.read()
                    base64_data = base64.b64encode(file_bytes).decode('ascii')

                    return {
                        "status": "success",
                        "disposition": f"Content was successfully read from {file_path} (binary)",
                        "file_path": str(file_path),
                        "mime_type": mime_type,
                        "encoding": "base64",
                        "data": base64_data
                    }
    except Exception as e:
        # Log the error and relay it back to the LLM
        error_message = f"Error in read_file_from_filesystem: {e}"
        print(error_message)
        return {
            "status": "error",
            "disposition": f"There was an error reading from the file: {str(e)}",
            "error": str(e)
        }

def write_file_wrapper(filename: str, content: str, tool_context=None) -> dict:
    """Wrapper function for write_file that passes the tool_context.

    Args:
        filename: The name of the file to write to
        content: The content to write to the file
        tool_context: The ToolContext object provided by the ADK

    Returns:
        dict: information about the status of the file writing operation
    """
    return write_file(filename, content, tool_context)

def read_file_wrapper(filename: str, tool_context=None) -> dict:
    """Wrapper function for read_file that passes the tool_context.

    Args:
        filename: The name of the file to read from
        tool_context: The ToolContext object provided by the ADK

    Returns:
        dict: information about the status of the file reading operation
    """
    return read_file(filename, tool_context)

def list_artifacts_wrapper(tool_context=None) -> dict:
    """Wrapper function for list_artifacts that passes the tool_context.

    Args:
        tool_context: The ToolContext object provided by the ADK

    Returns:
        dict: information about the available artifacts
    """
    return list_artifacts(tool_context)

def execute_shell_command(command: str) -> dict:
    """Executes a shell command with a 30-second timeout.
    Trusts the LLM to provide safe commands.

    Args:
        command: The shell command to execute

    Returns:
        dict: information about the command execution status and output
    """
    # Execute the command with timeout
    try:
        # Use threading with a timeout to prevent hanging
        result = {"status": "unknown", "output": "", "error": "", "command": command}
        process = None

        def target():
            nonlocal process, result
            try:
                # Use subprocess.run with shell=True to execute the command
                # This is intentional as we want to execute shell commands
                process = subprocess.run(
                    command,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=30  # 30-second timeout
                )

                result["status"] = "success" if process.returncode == 0 else "error"
                result["return_code"] = process.returncode
                result["output"] = process.stdout
                result["error"] = process.stderr
            except subprocess.TimeoutExpired:
                result["status"] = "timeout"
                result["error"] = "Command execution timed out after 30 seconds"
            except Exception as e:
                result["status"] = "error"
                result["error"] = str(e)

        # Start the command in a thread
        thread = threading.Thread(target=target)
        thread.start()
        thread.join(timeout=30)  # Wait for 30 seconds

        # If thread is still alive after timeout, the command is hanging
        if thread.is_alive():
            result["status"] = "timeout"
            result["error"] = "Command execution timed out after 30 seconds"
            # Try to terminate the process if it exists
            if process and hasattr(process, 'terminate'):
                process.terminate()

        # Format the result
        disposition = f"Command executed: {command}\n"
        if result["status"] == "success":
            disposition += "Command completed successfully."
        elif result["status"] == "error":
            disposition += f"Command failed with return code {result.get('return_code', 'unknown')}."
        elif result["status"] == "timeout":
            disposition += "Command timed out after 30 seconds."

        return {
            "status": result["status"],
            "disposition": disposition,
            "command": command,
            "output": result.get("output", ""),
            "error": result.get("error", ""),
            "return_code": result.get("return_code")
        }

    except Exception as e:
        # Log the error and relay it back to the LLM
        error_message = f"Error in execute_shell_command: {e}"
        print(error_message)
        return {
            "status": "error",
            "disposition": f"There was an error executing the command: {str(e)}",
            "command": command,
            "error": str(e)
        }

def execute_shell_command_wrapper(command: str, tool_context=None) -> dict:
    """Wrapper function for execute_shell_command that handles the tool_context.
    Trusts the LLM to provide safe commands.

    Args:
        command: The shell command to execute
        tool_context: The ToolContext object provided by the ADK (not used but included for consistency)

    Returns:
        dict: information about the command execution status and output
    """
    return execute_shell_command(command)

config = load_config()
agent_config = config.get("agent", {})
owner_config = config.get("owner", {})
owner_name = owner_config.get("name", "a person")

root_agent = Agent(
    name=f"{agent_config.get('name', 'myagent')}",
    model=agent_config.get('model', 'gemini-2.0-flash-exp'),
    description=(
        f"An agent representing {owner_config.get('name', 'a person')}"
    ),
    instruction=(
        f"You are {agent_config.get('name', 'myagent')}, and you speak and act on behalf of me, {owner_name}, according to my wishes. You can do various things, like relay messages to me. "
        f"Before using a tool, make sure you have all the information you need; ask the user for any missing information. "
        f"When using the shell command tool, I trust your judgment. You are responsible for ensuring commands are safe and appropriate. "
        f"Here are my special instructions: {agent_config.get('instructions', '')} "
        f"You must exhibit the following personality traits: {agent_config.get('personality', '')}"
    ),
    tools=[get_bio, relay_message, write_file_wrapper, read_file_wrapper, list_artifacts_wrapper, execute_shell_command_wrapper],
)