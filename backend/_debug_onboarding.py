"""Temporary debug script — delete after use."""
import asyncio, sys, tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

tmp = Path(tempfile.mkdtemp())
(tmp / "README.md").write_text("# My Project\n\nInstall: npm install\n")
(tmp / "package.json").write_text('{"name":"test"}')
(tmp / "src").mkdir()
(tmp / "src" / "index.js").write_text('console.log("hello");')

sys.path.insert(0, str(Path(__file__).parent))
from app.services.onboarding_service import OnboardingService, _SETUP_FILES
from app.services.intent_classifier import Intent


async def run():
    with patch("app.services.onboarding_service.settings") as ms, \
         patch("app.services.onboarding_service.GroqService") as MG:
        ms.project_root_path = str(tmp)
        mg = AsyncMock()
        mg.setup_guidance.return_value = "done"
        MG.return_value = mg

        svc = OnboardingService()
        print("root:", svc._root)
        print("scanner root:", svc._scanner.root)

        for fname in _SETUP_FILES:
            fpath = svc._root / fname
            print(f"  checking {fname}: exists={fpath.exists()}")
            if fpath.exists():
                try:
                    content, _ = svc._scanner.safe_read(fname)
                    print(f"    -> read OK, {len(content)} chars")
                except Exception as e:
                    print(f"    -> ERROR: {e}")

        result = await svc.handle(Intent.SETUP_GUIDANCE, project_analysis=None)
        print("result.error:", result.error)
        print("setup_guidance call_args:", mg.setup_guidance.call_args)


asyncio.run(run())
