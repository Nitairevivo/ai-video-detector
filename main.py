"""
CLI interface for the AI Video Detector.
Usage:
  python main.py detect video.mp4
  python main.py detect /folder/with/videos/
  python main.py label video.mp4 --ai
  python main.py train
  python main.py serve
"""
import typer
from pathlib import Path
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box

app = typer.Typer(help="AI Video Detector — reads file signatures to detect AI-generated videos")
console = Console()

SUPPORTED = {'.mp4', '.mov', '.mkv', '.webm', '.m4v'}


@app.command()
def detect(
    path: str = typer.Argument(..., help="Video file or folder to analyze"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show all signals"),
    deep: bool = typer.Option(False, "--deep", "-d", help="Run visual+frequency analysis (slower, ~10s per video)"),
):
    """Detect whether a video (or folder of videos) is AI-generated."""
    from analyzer import extract_features
    from models.classifier import get_classifier

    classifier = get_classifier()
    target = Path(path)

    if target.is_file():
        files = [target]
    elif target.is_dir():
        files = [f for f in target.rglob("*") if f.suffix.lower() in SUPPORTED]
        if not files:
            console.print("[red]No supported video files found.[/red]")
            raise typer.Exit(1)
    else:
        console.print(f"[red]Path not found: {path}[/red]")
        raise typer.Exit(1)

    import os as _os
    use_gemini = bool(_os.environ.get("GEMINI_API_KEY"))

    for f in files:
        console.print(f"\n[bold]Analyzing:[/bold] {f.name}")
        status_msg = "Running deep analysis (visual + frequency)..." if deep else "Reading file signatures..."
        with console.status(status_msg):
            result = extract_features(str(f), deep=deep)
            ml_prob, _ = classifier.predict(result.feature_vector)
            # Same fusion as the production server — CLI and API must agree
            from analyzer.ensemble import analyze_ensemble
            ens = analyze_ensemble(str(f), result, ml_prob, use_gemini=use_gemini)

        confidence = ens.confidence
        method = ens.method
        is_ai = ens.verdict == "ai_generated"
        if is_ai:
            color, verdict = "red", "AI GENERATED"
        elif ens.verdict == "ai_edited":
            color, verdict = "magenta", "REAL, AI-EDITED"
        else:
            color, verdict = "green", "REAL / AUTHENTIC"

        panel_content = (
            f"[bold {color}]{verdict}[/bold {color}]\n"
            f"Confidence: [bold]{confidence * 100:.1f}%[/bold]\n"
            f"Method: {method}\n"
        )
        if result.ai_tool:
            panel_content += f"Tool: [bold]{result.ai_tool}[/bold]\n"
        if not use_gemini:
            panel_content += "[dim]Gemini layer off (set GEMINI_API_KEY to enable)[/dim]\n"

        # Surface important warnings (signals already computed — no second ffprobe run)
        sig = result.signals or {}
        if deep and not sig.get("too_short_for_analysis"):
            panel_content += "\n[dim]Deep analysis: visual + frequency signals included[/dim]"
        if sig.get("too_short_for_analysis"):
            panel_content += "\n[yellow]Warning: video too short (<2s) — results unreliable[/yellow]"
        if sig.get("platform_reencoded"):
            panel_content += "\n[yellow]Note: re-encoded by a platform — some signals lost[/yellow]"
        if sig.get("metadata_is_stripped"):
            panel_content += "\n[yellow]Note: all metadata stripped — possible re-mux to hide origin[/yellow]"

        if ml_prob is None:
            panel_content += "\n[dim]Train the model with /label samples for ML-enhanced accuracy[/dim]"

        console.print(Panel(panel_content, box=box.ROUNDED))

        if verbose:
            table = Table(title="Detection Signals", box=box.SIMPLE)
            table.add_column("Signal", style="cyan")
            table.add_column("Value", style="white")
            for k, v in result.signals.items():
                if isinstance(v, float):
                    table.add_row(k, f"{v:.4f}")
                else:
                    table.add_row(k, str(v))
            console.print(table)


@app.command()
def label(
    path: str = typer.Argument(..., help="Video file to label"),
    ai: bool = typer.Option(None, "--ai/--real", help="Label as AI-generated or real"),
):
    """Add a labeled video sample to train the ML model."""
    from analyzer import extract_features
    from models.classifier import get_classifier

    if ai is None:
        console.print("[red]Specify --ai or --real[/red]")
        raise typer.Exit(1)

    f = Path(path)
    if not f.exists():
        console.print(f"[red]File not found: {path}[/red]")
        raise typer.Exit(1)

    with console.status("Extracting features..."):
        result = extract_features(str(f))

    classifier = get_classifier()
    classifier.add_sample(result.feature_vector, label=ai, source=f.name)
    label_str = "[red]AI[/red]" if ai else "[green]Real[/green]"
    console.print(f"Labeled {f.name} as {label_str}. Run [bold]train[/bold] to update the model.")


@app.command()
def train():
    """Train the ML model on all collected labeled samples."""
    from models.classifier import get_classifier
    classifier = get_classifier()
    with console.status("Training model..."):
        result = classifier.train()
    if "error" in result:
        console.print(f"[red]{result['error']}[/red]")
    else:
        console.print(f"[green]Model trained successfully![/green]")
        console.print(f"  Samples: {result['samples_used']} ({result['ai_samples']} AI, {result['real_samples']} Real)")
        console.print(f"  Cross-val AUC: {result['cv_auc_mean']:.3f} ± {result['cv_auc_std']:.3f}")


@app.command()
def importance():
    """Show which features the ML model relies on most."""
    from models.classifier import get_classifier
    classifier = get_classifier()
    imp = classifier.feature_importance()
    if imp is None:
        console.print("[red]Model not trained yet. Run [bold]train[/bold] first.[/red]")
        raise typer.Exit(1)

    table = Table(title="Feature Importance (top 15)", box=box.ROUNDED)
    table.add_column("Rank", style="dim", width=5)
    table.add_column("Feature", style="cyan")
    table.add_column("Importance", style="bold")
    table.add_column("Weight", style="green")

    total = sum(imp.values())
    for rank, (feat, val) in enumerate(list(imp.items())[:15], 1):
        bar = "█" * int(val / max(imp.values()) * 20)
        pct = f"{val / total * 100:.1f}%"
        table.add_row(str(rank), feat, f"{val:.4f}", f"{bar} {pct}")

    console.print(table)


@app.command()
def serve(
    host: str = typer.Option("0.0.0.0", help="Host to bind"),
    port: int = typer.Option(8000, help="Port to bind"),
):
    """Start the API server."""
    import uvicorn
    from api.server import app as fastapi_app
    console.print(f"[bold green]Starting server on {host}:{port}[/bold green]")
    uvicorn.run(fastapi_app, host=host, port=port)


if __name__ == "__main__":
    app()
