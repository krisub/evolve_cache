import sys
import os
import re
from openevolve.evaluation_result import EvaluationResult
import fcntl
import subprocess
import json
import traceback

FUNSEARCH_ROOT = "/users/krisub/funsearch"
WEBCACHE_ROOT = os.path.join(FUNSEARCH_ROOT, "webcache")
LIBCS_ROOT = "/users/krisub/funsearch/webcache/libCacheSim/libCacheSim"

if FUNSEARCH_ROOT not in sys.path:
    sys.path.append(FUNSEARCH_ROOT)
if WEBCACHE_ROOT not in sys.path:
    sys.path.append(WEBCACHE_ROOT)

try:
    from interface import WebCacheEvolve
except ImportError as e:
    print(f"--- ERROR ---")
    print(f"Could not import WebCacheEvolve from {WEBCACHE_ROOT}/interface.py")
    print(f"Python's current sys.path: {sys.path}")
    print(f"---------------")
    raise e

WEB_ARGS = [
    "--scaffolding",
    "FULL",
    "--percent",
    "--cache_sizes",
    "0.001",
    "0.01",
    "0.1",
    "--eval_cache_size",
    "0.1",
    "--trace",
    "CloudPhysics/w106.oracleGeneral.bin.zst",
    # '--byte' to optimize for byte_miss_ratio
]

ORIGINAL_CWD = os.getcwd()
try:
    os.chdir(FUNSEARCH_ROOT)
    webcache_interface = WebCacheEvolve(web_args=WEB_ARGS)
finally:
    os.chdir(ORIGINAL_CWD)

webcache_interface.code_dir = os.path.join(FUNSEARCH_ROOT, "webcache")
webcache_interface.build_dir = os.path.join(webcache_interface.code_dir, "build")

webcache_interface.llm_code_path = os.path.join(
    webcache_interface.code_dir,
    "libCacheSim/libCacheSim/cache/eviction/FullCodeEvolve/LLMCode.h",
)

webcache_interface.trace_dir = os.path.join(
    webcache_interface.code_dir, "../libCacheSim/data"
)
webcache_interface.trace_path = os.path.join(
    webcache_interface.trace_dir, webcache_interface.task_args.trace
)


LOCK_FILE_DIR = os.path.join(FUNSEARCH_ROOT, "build_locks")
LOCK_FILE = os.path.join(LOCK_FILE_DIR, ".openevolve.lock")
os.makedirs(LOCK_FILE_DIR, exist_ok=True)


def evaluate(program_content: str) -> EvaluationResult:

    if os.path.exists(program_content):
        try:
            with open(program_content, "r") as f:
                program_content = f.read()
        except Exception:
            pass

    with open(LOCK_FILE, "w") as f:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (IOError, BlockingIOError):
            print("=== SKIPPING EVALUATION: Build/Run lock busy ===")
            return EvaluationResult(
                metrics={"combined_score": float("-inf")},
                artifacts={"status": "SKIPPED - Build/Run lock busy"},
            )

        try:
            original_cwd = os.getcwd()
            try:
                local_code_path = "/users/krisub/evolve_cache/LLMCode.h"
                try:
                    with open(local_code_path, "w") as f_local:
                        f_local.write(program_content)
                except Exception:
                    pass

                os.chdir(FUNSEARCH_ROOT)

                build_success, build_stdout, build_stderr = webcache_interface.build(
                    program_content
                )

                if not build_success:

                    print("=" * 20 + " COMPILE ERROR " + "=" * 20)
                    print(build_stderr[:2000])
                    print("=" * 57)
                    return EvaluationResult(
                        metrics={"combined_score": float("-inf")},
                        artifacts={"compile_error": build_stderr[:2000]},
                    )

                run_success, results_dict, eval_logs = (
                    webcache_interface.run_experiment()
                )

                if not run_success:
                    run_error = eval_logs.get("stderr", "Run failed, no stderr")
                    print("=" * 20 + " RUNTIME ERROR " + "=" * 20)
                    print(run_error[:2000])
                    print("=" * 57)
                    return EvaluationResult(
                        metrics={"combined_score": float("-inf")},
                        artifacts={"run_error": run_error[:2000]},
                    )

                final_score = results_dict.get("score")

                if final_score is None:
                    print("=" * 20 + " EVALUATION ERROR " + "=" * 20)
                    return EvaluationResult(
                        metrics={"combined_score": float("-inf")},
                        artifacts={
                            "parse_error": "Interface returned no score.",
                            "results_str": str(results_dict),
                        },
                    )

                metrics_for_openevolve = {"combined_score": final_score}
                try:
                    mr_key = (
                        "byte_miss_ratio"
                        if webcache_interface.task_args.byte
                        else "miss_ratio"
                    )
                    for res in results_dict.get("results", []):
                        size_key = res.get(
                            "cache_size_percent", res.get("cache_size_mb", "unknown")
                        )
                        miss_ratio = res.get(mr_key)
                        if miss_ratio is not None:
                            metrics_for_openevolve[f"{mr_key}_{size_key}"] = float(
                                miss_ratio
                            )
                except Exception:
                    pass

                return EvaluationResult(
                    metrics=metrics_for_openevolve,
                    artifacts={"full_results_json": json.dumps(results_dict)},
                )

            except Exception as e:
                print("=" * 20 + " EVALUATOR EXCEPTION " + "=" * 20)
                print(traceback.format_exc())
                print("=" * 63)
                return EvaluationResult(
                    metrics={"combined_score": float("-inf")},
                    artifacts={"exception": str(e)},
                )

            finally:
                os.chdir(original_cwd)

        finally:
            fcntl.flock(f, fcntl.LOCK_UN)
