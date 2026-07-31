---
id: assemblyai
name: AssemblyAI
category: data
type: tool
icon: resources/icon.svg
tools: 5
implemented: 5
credentials: [ASSEMBLYAI_API_KEY]
requirements: [assemblyai]
version: "1.0.0"
---
# AssemblyAI

AssemblyAI tools.

## Tools

| id | name | status | what it does |
|----|------|--------|--------------|
| `assemblyai.assemblyai_get_subtitles` | AssemblyAI Get Subtitles | ✅ | Export your transcript in SRT or VTT format for subtitles and closed captions |
| `assemblyai.assemblyai_lemur` | AssemblyAI LeMUR | ✅ | Apply Large Language Models to spoken data using the AssemblyAI LeMUR framework |
| `assemblyai.assemblyai_list_transcripts` | AssemblyAI List Transcripts | ✅ | Retrieve a list of transcripts from AssemblyAI with filtering options |
| `assemblyai.assemblyai_poll_transcript` | AssemblyAI Poll Transcript | ✅ | Poll for the status of a transcription job using AssemblyAI |
| `assemblyai.assemblyai_start_transcript` | AssemblyAI Start Transcript | ✅ | Create a transcription job for an audio file using AssemblyAI with advanced options |

All 5 tools are implemented.

## Credentials

`ASSEMBLYAI_API_KEY`, an `api_key` argument on the call, or a `assemblyai_plugin` block in the config. Resolved once by the plugin — the tools never look it up themselves.
