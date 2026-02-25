# Using Ollama with last30days

This guide explains how to configure the `last30days` skill to use Ollama instead of (or alongside) OpenAI and xAI APIs.

## Overview

Ollama can be used as a local, self-hosted alternative for:
- **Reddit search**: Instead of OpenAI's API
- **X (Twitter) search**: Instead of xAI's API

When using Ollama, the model will generate search results in the same format as the API providers, and Claude (the assistant) will supervise and validate the responses.

## Prerequisites

1. **Install Ollama**: Download from [ollama.ai](https://ollama.ai) or install via:
   ```bash
   # macOS
   brew install ollama

   # Linux
   curl -fsSL https://ollama.ai/install.sh | sh
   ```

2. **Start Ollama service**:
   ```bash
   ollama serve
   ```

3. **Pull a capable model**: For best results, use models with good reasoning capabilities:
   ```bash
   # Recommended models (choose one):
   ollama pull llama3.1:70b      # Best quality
   ollama pull qwen2.5:32b       # Good balance
   ollama pull llama3.1:8b       # Faster, smaller
   ```

## Configuration

Edit `~/.config/last30days/.env` and add the following:

### Using Ollama for Reddit

```bash
# Enable Ollama for Reddit searches
USE_OLLAMA_REDDIT=true
OLLAMA_REDDIT_MODEL=llama3.1:70b

# Ollama base URL (default: http://localhost:11434)
OLLAMA_BASE_URL=http://localhost:11434
```

### Using Ollama for X (Twitter)

```bash
# Enable Ollama for X searches
USE_OLLAMA_X=true
OLLAMA_X_MODEL=llama3.1:70b

# Ollama base URL (default: http://localhost:11434)
OLLAMA_BASE_URL=http://localhost:11434
```

### Using Ollama for Both

```bash
# Enable Ollama for both Reddit and X
USE_OLLAMA_REDDIT=true
USE_OLLAMA_X=true

# Use the same or different models
OLLAMA_REDDIT_MODEL=llama3.1:70b
OLLAMA_X_MODEL=qwen2.5:32b

# Ollama base URL
OLLAMA_BASE_URL=http://localhost:11434
```

## Complete Configuration Example

Here's a complete `.env` file using Ollama:

```bash
# Ollama Configuration
USE_OLLAMA_REDDIT=true
USE_OLLAMA_X=true
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_REDDIT_MODEL=llama3.1:70b
OLLAMA_X_MODEL=llama3.1:70b

# Optional: Keep API keys for fallback or specific features
# OPENAI_API_KEY=sk-...
# XAI_API_KEY=xai-...

# Optional: Web search APIs (recommended for better coverage)
# BRAVE_API_KEY=...
# PARALLEL_API_KEY=...
```

## Usage

Once configured, use the skill normally:

```bash
# Basic search
python3 scripts/last30days.py "Claude Code tips"

# With options
python3 scripts/last30days.py "AI news" --deep --include-web
```

The tool will automatically use Ollama for the configured sources.

## Model Recommendations

| Model | Size | Speed | Quality | Best For |
|-------|------|-------|---------|----------|
| `llama3.1:70b` | Large | Slow | Excellent | Deep research, accuracy |
| `qwen2.5:32b` | Medium | Medium | Very Good | Balanced performance |
| `llama3.1:8b` | Small | Fast | Good | Quick searches, testing |
| `mistral:latest` | Medium | Medium | Good | General purpose |

## Remote Ollama Server

To use Ollama running on a remote server:

```bash
OLLAMA_BASE_URL=http://your-server:11434
```

## Troubleshooting

### Connection Error

If you see `[OLLAMA ERROR] Ollama API error`:

1. Check Ollama is running:
   ```bash
   curl http://localhost:11434/api/tags
   ```

2. Check the model is pulled:
   ```bash
   ollama list
   ```

3. Verify the base URL in your `.env` file

### Model Not Found

If you see `OLLAMA_REDDIT_MODEL not configured`:

1. Set the model in `.env`:
   ```bash
   OLLAMA_REDDIT_MODEL=llama3.1:70b
   ```

2. Pull the model:
   ```bash
   ollama pull llama3.1:70b
   ```

### Poor Results

If Ollama produces low-quality results:

1. Try a larger, more capable model:
   ```bash
   ollama pull llama3.1:70b
   OLLAMA_REDDIT_MODEL=llama3.1:70b
   ```

2. Remember: Claude will supervise the results, helping to filter and validate them

### Slow Performance

If searches are taking too long:

1. Use a smaller model:
   ```bash
   OLLAMA_REDDIT_MODEL=llama3.1:8b
   ```

2. Use `--quick` mode:
   ```bash
   python3 scripts/last30days.py "topic" --quick
   ```

3. Consider GPU acceleration for Ollama

## Hybrid Configuration

You can mix API services and Ollama:

```bash
# Use OpenAI for Reddit (has web_search tool)
OPENAI_API_KEY=sk-...

# Use Ollama for X (free alternative to xAI)
USE_OLLAMA_X=true
OLLAMA_X_MODEL=llama3.1:70b
```

## How It Works

1. **Query Generation**: Ollama receives a structured prompt asking it to find Reddit threads or X posts about a topic
2. **Result Production**: Ollama generates results in JSON format (URLs, titles, dates, relevance scores)
3. **Supervision**: Claude (the assistant) validates and supervises the Ollama output
4. **Integration**: Results are processed through the same pipeline as API results (scoring, deduplication, ranking)

## Performance Comparison

| Source | API Provider | Ollama (70B) | Ollama (8B) |
|--------|-------------|--------------|-------------|
| **Cost** | ~$0.01-0.05/search | Free | Free |
| **Speed** | Fast (2-5s) | Medium (10-30s) | Fast (3-10s) |
| **Quality** | Excellent | Very Good | Good |
| **Privacy** | Data sent to API | Fully local | Fully local |

## Notes

- Ollama models don't have real-time web access, so results may be based on training data
- Claude supervision helps ensure quality and relevance
- For best results, use Ollama with models 30B+ parameters
- API providers (OpenAI/xAI) have real-time data access and may produce more current results

## Next Steps

After configuring Ollama:

1. Test with a simple query:
   ```bash
   python3 scripts/last30days.py "test topic" --quick
   ```

2. Review the results and adjust models if needed

3. Consider using `--diagnose` to verify configuration:
   ```bash
   python3 scripts/last30days.py --diagnose
   ```

## Support

For issues or questions:
- Check Ollama logs: `journalctl -u ollama` (Linux) or Console.app (macOS)
- Verify model availability: `ollama list`
- Test Ollama directly: `ollama run llama3.1:70b "test prompt"`
