# Ollama Performance Guide

## Quality Over Speed Philosophy

When using Ollama, **there's no cost penalty for taking longer**. Unlike API providers that charge per token, Ollama runs locally and is completely free after setup. This means we should prioritize result quality over speed.

## Timeout Configuration

The default timeouts are designed for fast API responses (60-180s). For Ollama, you want **much longer timeouts** to let the model generate high-quality results.

### Recommended Settings

**For Best Results (Quality Priority):**
```bash
# Run without --quick flag to allow more time
python3 scripts/last30days.py "your topic"

# For comprehensive research (recommended with Ollama)
python3 scripts/last30days.py "your topic" --deep
```

The `--deep` flag gives Ollama plenty of time to generate thorough, high-quality results.

### Model Selection for Quality

Your installed models, ranked by quality:

| Model | Quality | Speed | RAM | Best For |
|-------|---------|-------|-----|----------|
| **qwen3:30b** | ★★★★★ Excellent | Slow | ~18GB | Best quality, worth the wait |
| **gemma3:27b** | ★★★★★ Excellent | Slow | ~17GB | Also excellent |
| **gpt-oss:20b** | ★★★★☆ Very Good | Medium | ~14GB | Good balance |
| **qwen3:8b** | ★★★★☆ Very Good | Fast | ~5GB | Recommended starting point |
| **deepseek-r1:8b** | ★★★★☆ Very Good | Fast | ~5GB | Good for reasoning tasks |
| **gemma3:12b** | ★★★☆☆ Good | Fast | ~8GB | Decent results |
| **qwen3:4b** | ★★★☆☆ Good | Very Fast | ~2.5GB | Too small for this task |
| **gemma3:4b** | ★★☆☆☆ Fair | Very Fast | ~3GB | Too small for this task |

### Recommended Configuration

**For Production Use (Best Quality):**
```bash
# ~/.config/last30days/.env
USE_OLLAMA_REDDIT=true
USE_OLLAMA_X=true
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_REDDIT_MODEL=qwen3:30b
OLLAMA_X_MODEL=qwen3:30b
```

**For Faster Testing:**
```bash
OLLAMA_REDDIT_MODEL=qwen3:8b
OLLAMA_X_MODEL=qwen3:8b
```

## Real-World Performance

Based on testing with your models:

### qwen3:4b / gemma3:4b (Small Models)
- ⚠️ **Too slow** - Takes 60-90s but often times out before completing
- ⚠️ **Lower quality** - Smaller context window, less reasoning ability
- **Verdict:** Not recommended for this task

### qwen3:8b / deepseek-r1:8b (Medium Models)
- ✅ **Good balance** - Takes 2-4 minutes per source
- ✅ **Good quality** - Produces useful, relevant results
- ✅ **Reasonable speed** - Total research: 5-10 minutes
- **Verdict:** **Recommended starting point**

### qwen3:30b / gemma3:27b (Large Models)
- ✅ **Excellent quality** - Best reasoning, most thorough results
- ⏱️ **Slower** - Takes 5-8 minutes per source
- ⏱️ **Total research:** 15-20 minutes
- **Verdict:** **Best quality, worth the wait if you have time**

## Usage Tips

### 1. Let It Run
Don't interrupt Ollama mid-generation. The model needs time to:
- Understand the topic deeply
- Generate comprehensive search results
- Format proper JSON output
- Ensure accuracy and relevance

### 2. Use --deep for Thorough Research
```bash
python3 scripts/last30days.py "topic" --deep
```
This removes speed constraints and lets Ollama work properly.

### 3. Monitor Progress
The script shows real-time progress:
```
⏳ Reddit Scrolling through comments...
⏳ X Finding the hot takes...
```

If you see these messages, Ollama is working. Be patient!

### 4. Check Ollama's Activity
In another terminal:
```bash
# Monitor Ollama's resource usage
ollama ps

# Check if model is loaded
ollama list
```

## Troubleshooting Timeouts

If you still get timeouts:

1. **Use a larger model** - 8B minimum, 30B recommended
2. **Remove --quick flag** - Let it take the time it needs
3. **Use --deep** - Extends all timeouts appropriately
4. **Check Ollama** - Make sure it's not throttled:
   ```bash
   # Check Ollama status
   curl http://localhost:11434/api/tags
   ```

## The Bottom Line

**With Ollama, patience = quality.**

- Small models (4B): ❌ Don't work well
- Medium models (8B): ✅ Good results in 5-10 min
- Large models (30B): ✅✅ Excellent results in 15-20 min

Unlike API providers, **you're not paying per minute**. Let Ollama take the time it needs to generate high-quality research results.

## Comparison: Ollama vs API Providers

| Aspect | API (OpenAI/xAI) | Ollama (30B model) |
|--------|------------------|-------------------|
| **Speed** | 30-60 seconds | 15-20 minutes |
| **Cost per search** | $0.02-0.10 | $0.00 |
| **Quality** | Excellent | Excellent |
| **Real-time data** | Yes (web access) | No (model knowledge) |
| **Privacy** | Data sent to API | Fully local |
| **Best for** | Speed, latest info | Cost, privacy, quality |

## Recommendation

For the **best Ollama experience:**

```bash
# Use your best model
cat > ~/.config/last30days/.env << 'EOF'
USE_OLLAMA_REDDIT=true
USE_OLLAMA_X=true
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_REDDIT_MODEL=qwen3:30b
OLLAMA_X_MODEL=qwen3:30b
EOF

# Run without time pressure
python3 scripts/last30days.py "your topic" --deep

# Get coffee, come back to excellent results ☕
```
