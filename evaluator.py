import sys
import os
import re
from openevolve import EvaluationResult
import fcntl
import subprocess

FUNSEARCH_ROOT = "/users/krisub/funsearch"
WEBCACHE_ROOT = os.path.join(FUNSEARCH_ROOT, "webcache")
LIBCS_ROOT = "/users/krisub/funsearch/webcache/libCacheSim/libCacheSim"

if FUNSEARCH_ROOT not in sys.path:
    sys.path.append(FUNSEARCH_ROOT)

try:
    from interface import WebCacheEvolve
except ImportError as e:
    print(f"--- ERROR ---")
    print(f"Could not import WebCacheEvolve from {WEBCACHE_ROOT}/interface.py")
    # print(f"Please check your FUNSEARCH_ROOT path. It is currently: {FUNSEARCH_ROOT}")
    print(f"Python's current sys.path: {sys.path}")
    print(f"---------------")
    raise e

WEB_ARGS = [
    "--scaffolding", "FULL",
    "--percent",
    "--cache_sizes", "0.1", "1", "10",
    "--eval_cache_size", "10",
    "--trace", "CloudPhysics/w106.oracleGeneral.bin.zst" 
    # '--byte' to optimize for byte_miss_ratio
]

ORIGINAL_CWD = os.getcwd()
try:
    os.chdir(WEBCACHE_ROOT)
    webcache_interface = WebCacheEvolve(web_args=WEB_ARGS)
finally:
    os.chdir(ORIGINAL_CWD)

webcache_interface.code_dir = os.path.join(FUNSEARCH_ROOT, "webcache")
webcache_interface.build_dir = os.path.join(webcache_interface.code_dir, "build")

webcache_interface.llm_code_path = os.path.join(
    webcache_interface.code_dir, 
    "libCacheSim/libCacheSim/cache/eviction/FullCodeEvolve/LLMCode.h"
)

webcache_interface.trace_dir = os.path.join(LIBCS_ROOT, "data")
webcache_interface.trace_path = os.path.join(webcache_interface.trace_dir, webcache_interface.task_args.trace)

LOCK_FILE_DIR = os.path.join(FUNSEARCH_ROOT, "build_locks")
LOCK_FILE = os.path.join(LOCK_FILE_DIR, ".openevolve.lock")
os.makedirs(LOCK_FILE_DIR, exist_ok=True)


def evaluate_program(program_content: str) -> EvaluationResult:
    """
    This function is called by OpenEvolve to evaluate one program.
    It uses the existing funsearch/interface.py to do all the heavy lifting.
    """

    with open(LOCK_FILE, "w") as f:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (IOError, BlockingIOError):
            return EvaluationResult(
                score=float("-inf"),
                fitness=float("-inf"),
                metrics={"status": "SKIPPED - Build/Run lock busy"}
            )

        original_cwd = os.getcwd()
        try:
            os.chdir(FUNSEARCH_ROOT)

            build_success, build_stdout, build_stderr = webcache_interface.build(program_content)

            if not build_success:
                return EvaluationResult(
                    score=float("-inf"),
                    fitness=float("-inf"),
                    metrics={"compile_error": build_stderr[:2000]} 
                )

            run_success, results_dict, eval_logs = webcache_interface.run_experiment()

            if not run_success:
                return EvaluationResult(
                    score=float("-inf"),
                    fitness=float("-inf"),
                    metrics={"run_error": eval_logs.get("stderr", "Run failed, no stderr")[:2000]}
                )

            final_score = results_dict.get("score") 
            
            if final_score is None:
                 return EvaluationResult(
                    score=float("-inf"),
                    fitness=float("-inf"),
                    metrics={"parse_error": "Interface returned no score.", "results": str(results_dict)}
                )

            # OpenEvolve maximizes score, and the score is hit_rate (1 - miss_ratio),
            # so a higher score is already better.
            return EvaluationResult(
                score=final_score,
                fitness=final_score,
                metrics=results_dict
            )

        except Exception as e:
            return EvaluationResult(
                score=float("-inf"),
                fitness=float("-inf"),
                metrics={"exception": str(e)}
            )
        
        finally:
            os.chdir(original_cwd)
            fcntl.flock(f, fcntl.LOCK_UN)