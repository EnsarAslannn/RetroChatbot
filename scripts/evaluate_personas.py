import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

from app.gemini_service import GeminiChatService


CASES = [
    {"era": "1998", "prompt": "TikTok'ta nasıl video paylaşırım?"},
    {"era": "1998", "prompt": "iPhone almak istiyorum, hangi modeli seçmeliyim?"},
    {"era": "1998", "prompt": "Arkadaşlarımla internette nasıl sohbet ederim?"},
    {"era": "2058", "prompt": "2058'te şehir içi ulaşım kesin olarak nasıl olacak?"},
    {"era": "2058", "prompt": "2058'te insanlar nasıl müzik dinliyor?"},
    {"era": "2058", "prompt": "Geleceğe dair anlattıkların kesin mi?"},
]


def run_evaluations(service: GeminiChatService) -> list[dict]:
    results = []
    for case in CASES:
        response = service.reply(case["prompt"], [], era=case["era"])
        evaluation = service.evaluate_persona_response(case["era"], case["prompt"], response)
        results.append({**case, "response": response, **evaluation})
    return results


def main() -> int:
    load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        print("GEMINI_API_KEY gerekli.", file=sys.stderr)
        return 2
    results = run_evaluations(GeminiChatService(api_key=api_key))
    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0 if all(item["passed"] for item in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
