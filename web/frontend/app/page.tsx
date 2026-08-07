import Link from "next/link";
import { ClipMock } from "@/components/landing/ClipMock";
import {
  IconCaptions,
  IconCheck,
  IconCrop,
  IconDownload,
  IconFace,
  IconGlobe,
  IconSparkle,
  IconUpload,
  IconWand,
} from "@/components/landing/Icons";

const FEATURES = [
  {
    icon: IconWand,
    title: "Finds the best moments",
    body: "KatGai Reel watches and transcribes the full video, then scores every moment for hook strength and pacing — so you skip the scrubbing.",
  },
  {
    icon: IconCrop,
    title: "Reframes automatically",
    body: "Every clip is re-cropped to vertical, square, portrait, or landscape, with optional face tracking so speakers stay centered as they move.",
  },
  {
    icon: IconCaptions,
    title: "Burns in styled captions",
    body: "Plain, word-by-word, or highlight-style captions are rendered directly into the clip — no separate caption file to sync yourself.",
  },
];

const STEPS = [
  {
    icon: IconUpload,
    title: "Upload your video",
    body: "Drop in a podcast, stream VOD, webinar, or talk — any length. The file goes straight to secure storage from your browser.",
  },
  {
    icon: IconSparkle,
    title: "AI finds the clips",
    body: "Transcription, scoring, cutting, reframing, and captioning run as one job. Watch progress update live, step by step.",
  },
  {
    icon: IconDownload,
    title: "Review and download",
    body: "Preview every clip with its hook score, pick the winners, and download them ready to post — or send straight to your editor.",
  },
];

const DETAILS = [
  {
    icon: IconCrop,
    title: "5 aspect ratios",
    body: "Original, vertical (9:16), square (1:1), portrait, and landscape — pick per job.",
  },
  {
    icon: IconFace,
    title: "Face tracking",
    body: "Toggle tracked reframing so the crop follows whoever's speaking instead of a fixed center crop.",
  },
  {
    icon: IconCaptions,
    title: "3 caption styles",
    body: "Plain subtitles, word-by-word reveal, or highlighted keyword style — burned in, not a separate file.",
  },
  {
    icon: IconGlobe,
    title: "English, Hindi & Hinglish",
    body: "Auto-detect the spoken language, or pin it — including mixed Hinglish transcription.",
  },
];

const PLANS = [
  {
    name: "Free",
    price: "$0",
    period: "forever",
    tagline: "Try the full pipeline on a couple of uploads.",
    features: ["3 clip jobs / month", "Up to 15 min source video", "Vertical & square reframing", "Watermarked exports"],
    cta: "Start free",
    highlighted: false,
  },
  {
    name: "Creator",
    price: "$19",
    period: "/ month",
    tagline: "For creators publishing clips every week.",
    features: [
      "30 clip jobs / month",
      "Up to 2 hr source video",
      "All aspect ratios + face tracking",
      "All caption styles",
      "No watermark",
    ],
    cta: "Start free trial",
    highlighted: true,
  },
  {
    name: "Studio",
    price: "$49",
    period: "/ month",
    tagline: "For teams and agencies running multiple shows.",
    features: [
      "Unlimited clip jobs",
      "Up to 5 hr source video",
      "Priority processing queue",
      "Shared job history",
    ],
    cta: "Talk to us",
    highlighted: false,
  },
];

export default function LandingPage() {
  return (
    <>
      {/* ---------------------------------------------------------- Hero */}
      <section className="relative overflow-hidden">
        <div className="pointer-events-none absolute inset-0 bg-signal-glow" />
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0 opacity-[0.07]"
          style={{
            backgroundImage:
              "linear-gradient(to right, #fff 1px, transparent 1px), linear-gradient(to bottom, #fff 1px, transparent 1px)",
            backgroundSize: "48px 48px",
            maskImage: "linear-gradient(to bottom, black, transparent)",
          }}
        />

        <div className="container-page relative grid grid-cols-1 items-center gap-12 py-16 sm:py-20 lg:grid-cols-2 lg:py-28">
          <div className="animate-fade-up">
            <div className="badge mb-6 border border-ink-700 bg-ink-900/80 text-ink-300">
              <span className="h-1.5 w-1.5 rounded-full bg-signal-500" />
              Now transcribing English, Hindi & Hinglish
            </div>

            <h1 className="font-display text-4xl font-bold leading-[1.08] tracking-tight text-ink-50 sm:text-5xl lg:text-[3.4rem]">
              Your long video has{" "}
              <span className="bg-gradient-to-r from-signal-400 to-signal-600 bg-clip-text text-transparent">
                a dozen clips
              </span>{" "}
              hiding in it.
            </h1>

            <p className="mt-6 max-w-xl text-lg leading-relaxed text-ink-300">
              Upload one long video. KatGai Reel transcribes it, finds the
              moments worth clipping, reframes them for vertical or square,
              and burns in styled captions — so you get a stack of
              ready-to-post shorts back, not homework.
            </p>

            <div className="mt-9 flex flex-col gap-3 sm:flex-row">
              <Link href="/login" className="btn-primary text-base">
                Upload your first video
                <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth={2}>
                  <path d="M5 12h14M13 6l6 6-6 6" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </Link>
              <Link href="#how-it-works" className="btn-secondary text-base">
                See how it works
              </Link>
            </div>

            <p className="mt-5 text-sm text-ink-500">
              No credit card required. 3 clip jobs free every month.
            </p>
          </div>

          <div className="animate-fade-up [animation-delay:120ms]">
            <ClipMock />
          </div>
        </div>
      </section>

      {/* ------------------------------------------------------ Features */}
      <section className="border-t border-ink-800/80 bg-ink-900/40 py-20 sm:py-24">
        <div className="container-page">
          <div className="max-w-2xl">
            <h2 className="font-display text-3xl font-bold tracking-tight text-ink-50 sm:text-4xl">
              One upload, the whole editing pass done for you
            </h2>
            <p className="mt-4 text-lg text-ink-300">
              Everything an editor would do by hand — finding the hook,
              reframing for mobile, adding captions — runs automatically on
              every video you send in.
            </p>
          </div>

          <div className="mt-14 grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
            {FEATURES.map((f) => (
              <div key={f.title} className="card p-7">
                <div className="mb-5 grid h-12 w-12 place-items-center rounded-xl bg-signal-500/10 text-signal-400">
                  <f.icon />
                </div>
                <h3 className="font-display text-lg font-bold text-ink-50">{f.title}</h3>
                <p className="mt-2 text-[15px] leading-relaxed text-ink-300">{f.body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* --------------------------------------------------- How it works */}
      <section id="how-it-works" className="scroll-mt-16 py-20 sm:py-24">
        <div className="container-page">
          <div className="max-w-2xl">
            <h2 className="font-display text-3xl font-bold tracking-tight text-ink-50 sm:text-4xl">
              How it works
            </h2>
            <p className="mt-4 text-lg text-ink-300">
              Three steps, one job that runs end to end while you do
              something else.
            </p>
          </div>

          <div className="relative mt-14 grid grid-cols-1 gap-8 sm:grid-cols-3">
            <div
              aria-hidden
              className="absolute left-0 right-0 top-6 hidden h-px bg-gradient-to-r from-transparent via-ink-700 to-transparent sm:block"
            />
            {STEPS.map((s, i) => (
              <div key={s.title} className="relative">
                <div className="relative z-10 mb-5 grid h-12 w-12 place-items-center rounded-full border border-ink-600 bg-ink-950 text-signal-400">
                  <s.icon className="h-5 w-5" />
                </div>
                <p className="mb-1 text-xs font-semibold uppercase tracking-wider text-ink-500">
                  Step {i + 1}
                </p>
                <h3 className="font-display text-lg font-bold text-ink-50">{s.title}</h3>
                <p className="mt-2 text-[15px] leading-relaxed text-ink-300">{s.body}</p>
              </div>
            ))}
          </div>

          {/* progress-style status strip, mirrors the real job pipeline */}
          <div className="card mt-14 overflow-x-auto p-5">
            <div className="flex min-w-[640px] items-center justify-between text-xs font-medium text-ink-400">
              {["Transcribing", "Scoring clips", "Cutting", "Reframing", "Captioning", "Uploading", "Done"].map(
                (label, i) => (
                  <div key={label} className="flex flex-1 items-center">
                    <div className="flex flex-col items-center gap-2">
                      <div
                        className={`h-2.5 w-2.5 rounded-full ${
                          i === 6 ? "bg-signal-500" : "bg-ink-600"
                        }`}
                      />
                      <span className={i === 6 ? "text-signal-400" : ""}>{label}</span>
                    </div>
                    {i < 6 && <div className="mx-2 h-px flex-1 bg-ink-700" />}
                  </div>
                )
              )}
            </div>
          </div>
        </div>
      </section>

      {/* -------------------------------------------------------- Details */}
      <section className="border-t border-ink-800/80 bg-ink-900/40 py-20 sm:py-24">
        <div className="container-page">
          <h2 className="font-display text-3xl font-bold tracking-tight text-ink-50 sm:text-4xl">
            Tuned per job, not one-size-fits-all
          </h2>
          <div className="mt-12 grid grid-cols-1 gap-x-8 gap-y-10 sm:grid-cols-2">
            {DETAILS.map((d) => (
              <div key={d.title} className="flex gap-4">
                <div className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-ink-800 text-aux-400">
                  <d.icon className="h-5 w-5" />
                </div>
                <div>
                  <h3 className="font-display text-base font-bold text-ink-50">{d.title}</h3>
                  <p className="mt-1.5 text-[15px] leading-relaxed text-ink-300">{d.body}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* -------------------------------------------------------- Pricing */}
      <section id="pricing" className="scroll-mt-16 py-20 sm:py-24">
        <div className="container-page">
          <div className="max-w-2xl">
            <h2 className="font-display text-3xl font-bold tracking-tight text-ink-50 sm:text-4xl">
              Simple pricing, cancel anytime
            </h2>
            <p className="mt-4 text-lg text-ink-300">
              Start free. Upgrade when you outgrow the free tier&apos;s monthly
              clip jobs.
            </p>
          </div>

          <div className="mt-14 grid grid-cols-1 gap-6 lg:grid-cols-3">
            {PLANS.map((plan) => (
              <div
                key={plan.name}
                className={`card relative flex flex-col p-8 ${
                  plan.highlighted ? "border-signal-500/60 shadow-glow" : ""
                }`}
              >
                {plan.highlighted && (
                  <span className="badge absolute -top-3 left-8 bg-signal-500 text-ink-950">
                    Most popular
                  </span>
                )}
                <h3 className="font-display text-xl font-bold text-ink-50">{plan.name}</h3>
                <p className="mt-1 text-sm text-ink-400">{plan.tagline}</p>
                <div className="mt-6 flex items-baseline gap-1.5">
                  <span className="font-display text-4xl font-bold text-ink-50">{plan.price}</span>
                  <span className="text-sm text-ink-400">{plan.period}</span>
                </div>
                <ul className="mt-7 flex-1 space-y-3">
                  {plan.features.map((f) => (
                    <li key={f} className="flex items-start gap-2.5 text-[15px] text-ink-200">
                      <IconCheck className="mt-0.5 h-4 w-4 shrink-0 text-signal-500" />
                      {f}
                    </li>
                  ))}
                </ul>
                <Link
                  href="/login"
                  className={`mt-8 ${plan.highlighted ? "btn-primary" : "btn-secondary"}`}
                >
                  {plan.cta}
                </Link>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ------------------------------------------------------- Final CTA */}
      <section className="border-t border-ink-800/80 py-20 sm:py-24">
        <div className="container-page">
          <div className="card relative overflow-hidden px-8 py-16 text-center sm:px-16">
            <div className="pointer-events-none absolute inset-0 bg-signal-glow opacity-70" />
            <div className="relative">
              <h2 className="font-display text-3xl font-bold tracking-tight text-ink-50 sm:text-4xl">
                Stop scrubbing your own footage for clips
              </h2>
              <p className="mx-auto mt-4 max-w-xl text-lg text-ink-300">
                Upload a video and let KatGai Reel hand you back the moments
                worth posting.
              </p>
              <Link href="/login" className="btn-primary mt-8 inline-flex text-base">
                Get started free
              </Link>
            </div>
          </div>
        </div>
      </section>
    </>
  );
}
