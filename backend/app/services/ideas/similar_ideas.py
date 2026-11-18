from typing import Any
from urllib.parse import urlparse

from app.utils.logger import logger

# The side panel shows one compact line per result, so it can carry more of them.
MAX_COMPARABLES = 8
MAX_RESEARCH_TOPICS = 5


class SimilarIdeas:
    """
    Class responsible for finding similar startup ideas based on public datasets
    or OpenAI-powered semantic searches.
    """

    _blocked_search_hosts = {
        "google.com",
        "bing.com",
        "search.yahoo.com",
        "duckduckgo.com",
        "perplexity.ai",
    }

    _grounded_search_system_prompt = """
    You are a market intelligence analyst.

    Use live public web search results to build a founder-ready competitive landscape with exact citations.
    Return valid JSON only.
    """

    _grounded_search_prompt = """
    Research the startup idea below using live public web results and return JSON with exactly this shape:

    {{
      "comparables": [
        {{
          "title": "string",
          "url": "https://exact-public-url-or-null",
          "summary": "string",
          "why_similar": "string",
          "signal": "string"
        }}
      ],
      "research_topics": [
        {{
          "title": "string",
          "url": "https://primary-citation-url-or-null",
          "sources": [
            {{
              "title": "string",
              "url": "https://exact-public-url",
              "publisher": "string"
            }}
          ],
          "why_it_matters": "string",
          "what_to_validate": "string"
        }}
      ]
    }}

    Requirements:
    - Return 8 comparables and 5 research topics when the web results support them; return fewer rather than pad with weak matches.
    - Prefer real, recognizable companies when confident; otherwise use a precise category label.
    - For comparable URLs, prefer the official homepage or product page.
    - For research sources, prefer exact public pages from authoritative publishers, government agencies, trade associations, reputable research firms, or public market reports.
    - Never return Google, Bing, Yahoo, DuckDuckGo, Perplexity, or other search result URLs.
    - Never fabricate or guess a URL. If an exact URL is not confidently verified, use null for that field or omit that source entry.
    - Keep summaries concise and factual. Do not invent statistics.
    - Keep each sentence to one line of business-relevant insight.

    Startup idea: "{idea_description}"
    """

    _fallback_prompt = """
    You are a strategy analyst preparing a concise competitive landscape brief for a startup founder.

    Given the following startup idea: "{idea_description}", return Markdown using exactly this structure:

    # Similar Landscape
    ## Comparable Companies
    ### [Company or product name]
    - URL: [exact public website URL in markdown link format when confidently verified, otherwise write "Not confidently verified"]
    - Summary: [one-line positioning]
    - Why Similar: [one-line explanation]
    - Distinguishing Signal: [one-line differentiator, traction signal, or category note]

    Repeat the comparable company entry format for 8 companies or product categories.

    ## Research Watchlist
    ### [Research topic or market thread]
    - Suggested Sources: [1-3 exact public markdown links only; if you cannot verify an exact public URL, say "No exact public citation confidently verified yet."]
    - Why It Matters: [one-line reason]
    - What To Validate: [specific thing the founder should confirm]

    Repeat the research entry format for 5 topics.

    Rules:
    - Be concrete, concise, and professional.
    - Prefer real, recognizable companies when you are confident.
    - If you are not confident about a company, use a category label instead of inventing a fake company.
    - Never use Google, Bing, Yahoo, DuckDuckGo, Perplexity, or generic search result URLs.
    - Do not invent statistics or source URLs.
    - Keep each bullet to a single sentence.
    """

    def __init__(self, model=None):
        """
        Initialize the SimilarIdeas service with an optional reference to the ManifestManager.
        """
        logger.info("[SimilarIdeas] Initializing SimilarIdeas service")
        self._model = model  # Model object (optional)
        self.results = ""  # Store markdown results
        logger.info("[SimilarIdeas] Successfully initialized service")

    def update(self):
        """
        Update similar ideas if idea has changed.
        """
        logger.info("[SimilarIdeas] Starting similar ideas update")
        if self._model and hasattr(self._model, "idea"):
            description = getattr(self._model.idea, "description", None)
            logger.info(
                f"[SimilarIdeas] Updating similar ideas for idea (length: {len(description) if description else 0})"
            )
            if description:
                logger.debug(f"[SimilarIdeas] Idea description preview: {description[:100]}...")
                self.find(description)
            else:
                logger.warning("[SimilarIdeas] Empty idea description provided")
        else:
            logger.warning("[SimilarIdeas] Idea description not available for similar ideas update")

    def find(self, idea_description):
        """
        Use the AI layer to find similar ideas based on semantic similarity to the input description.
        """
        logger.info(
            f"[SimilarIdeas] Starting similar ideas search (description length: {len(idea_description)})"
        )
        logger.debug(f"[SimilarIdeas] Idea description preview: {idea_description[:100]}...")

        if not self._model or not hasattr(self._model, "ai_layer"):
            logger.warning(
                "[SimilarIdeas] AI layer not available for description similarity search"
            )
            return ""

        try:
            if hasattr(self._model.ai_layer, "perform_web_search_json"):
                logger.info("[SimilarIdeas] Sending grounded structured search request to AI layer")
                grounded_result = self._model.ai_layer.perform_web_search_json(
                    self._grounded_search_prompt.format(idea_description=idea_description),
                    system_prompt=self._grounded_search_system_prompt.strip(),
                )
                grounded_payload = grounded_result.get("data") or {}
                rendered_markdown = self._render_grounded_markdown(grounded_payload)
                if rendered_markdown.strip():
                    self.results = rendered_markdown
                    logger.info(
                        f"[SimilarIdeas] Successfully built grounded similar ideas (response length: {len(rendered_markdown)})"
                    )
                    logger.debug(
                        f"[SimilarIdeas] Grounded response preview: {rendered_markdown[:100]}..."
                    )
                    return self.results
                logger.warning(
                    "[SimilarIdeas] Grounded structured search returned no renderable content"
                )
        except Exception as e:
            logger.warning(
                f"[SimilarIdeas] Grounded structured search failed, falling back to text generation: {e}"
            )

        prompt = self._fallback_prompt.format(idea_description=idea_description)
        logger.debug(f"[SimilarIdeas] Fallback prompt preview: {prompt[:100]}...")

        try:
            logger.info("[SimilarIdeas] Sending fallback markdown request to AI layer")
            response = self._model.ai_layer.generate_rich_text(
                [{"role": "user", "content": prompt}],
                format_type="markdown",
            )

            self.results = response
            logger.info(
                f"[SimilarIdeas] Successfully found similar ideas (response length: {len(response)})"
            )
            logger.debug(f"[SimilarIdeas] Response preview: {response[:100]}...")
            return self.results
        except Exception as e:
            logger.error(f"[SimilarIdeas] Failed to generate similar ideas: {str(e)}")
            return ""

    def _render_grounded_markdown(self, payload: dict[str, Any]) -> str:
        """Render grounded structured search results into the existing markdown contract."""
        comparables = payload.get("comparables") if isinstance(payload, dict) else []
        research_topics = payload.get("research_topics") if isinstance(payload, dict) else []

        lines: list[str] = [
            "# Similar Landscape",
            "## Comparable Companies",
        ]

        valid_comparables = [item for item in comparables if isinstance(item, dict)]
        for comparable in valid_comparables[:MAX_COMPARABLES]:
            title = self._clean_text(comparable.get("title"))
            if not title:
                continue

            url = self._normalize_public_url(comparable.get("url"))
            summary = self._clean_text(comparable.get("summary"))
            why_similar = self._clean_text(comparable.get("why_similar"))
            signal = self._clean_text(comparable.get("signal"))

            lines.append(f"### {title}")
            if url:
                lines.append(f"- URL: [{self._link_label(title, url)}]({url})")
            else:
                lines.append("- URL: Not confidently verified")
            lines.append(f"- Summary: {summary or 'No concise positioning available.'}")
            lines.append(
                f"- Why Similar: {why_similar or 'Targets a nearby workflow or customer need.'}"
            )
            lines.append(
                f"- Distinguishing Signal: {signal or 'Category or traction details require follow-up.'}"
            )
            lines.append("")

        lines.append("## Research Watchlist")

        valid_topics = [item for item in research_topics if isinstance(item, dict)]
        for topic in valid_topics[:MAX_RESEARCH_TOPICS]:
            title = self._clean_text(topic.get("title"))
            if not title:
                continue

            sources = self._normalize_sources(topic.get("sources"))
            topic_url = self._normalize_public_url(topic.get("url")) or (
                sources[0]["url"] if sources else None
            )
            why_it_matters = self._clean_text(topic.get("why_it_matters"))
            what_to_validate = self._clean_text(topic.get("what_to_validate"))

            if topic_url:
                lines.append(f"### [{title}]({topic_url})")
            else:
                lines.append(f"### {title}")

            if sources:
                rendered_sources = ", ".join(
                    f"[{source['title']}]({source['url']})" for source in sources[:3]
                )
                lines.append(f"- Suggested Sources: {rendered_sources}")
            else:
                lines.append(
                    "- Suggested Sources: No exact public citation confidently verified yet."
                )

            lines.append(
                f"- Why It Matters: {why_it_matters or 'This topic affects market sizing, prioritization, or positioning.'}"
            )
            lines.append(
                f"- What To Validate: {what_to_validate or 'Validate the most decision-relevant assumption before committing roadmap time.'}"
            )
            lines.append("")

        return "\n".join(lines).strip()

    def _normalize_sources(self, sources: Any) -> list[dict[str, str]]:
        """Keep only sources with exact public URLs."""
        normalized: list[dict[str, str]] = []

        if not isinstance(sources, list):
            return normalized

        seen = set()
        for source in sources:
            if not isinstance(source, dict):
                continue

            url = self._normalize_public_url(source.get("url"))
            if not url or url in seen:
                continue

            seen.add(url)
            title = (
                self._clean_text(source.get("title"))
                or self._clean_text(source.get("publisher"))
                or self._hostname_label(url)
            )
            normalized.append({"title": title, "url": url})

        return normalized

    def _normalize_public_url(self, value: Any) -> str | None:
        """Allow only exact public URLs and block generic search-result pages."""
        candidate = self._clean_text(value)
        if not candidate:
            return None

        try:
            parsed = urlparse(candidate)
        except Exception:
            return None

        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return None

        hostname = parsed.netloc.lower()
        if hostname.startswith("www."):
            hostname = hostname[4:]

        if hostname in self._blocked_search_hosts:
            path = parsed.path or ""
            if (
                hostname != "perplexity.ai"
                or path.startswith("/search")
                or path.startswith("/discover")
            ):
                return None

        return candidate

    @staticmethod
    def _clean_text(value: Any) -> str:
        if value is None:
            return ""
        return " ".join(str(value).split()).strip()

    @staticmethod
    def _hostname_label(url: str) -> str:
        hostname = urlparse(url).netloc.lower()
        return hostname[4:] if hostname.startswith("www.") else hostname

    def _link_label(self, title: str, url: str) -> str:
        label = self._clean_text(title)
        return label or self._hostname_label(url)
