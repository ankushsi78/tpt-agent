import React, { useState, useEffect } from 'react';
import { base44 } from '@/api/base44Client';
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { TrendingUp, Check, ArrowRight, ArrowLeft, RotateCcw, Printer, FlaskConical } from 'lucide-react';

// ─────────────────────────────────────────────────────────────────────────────
// Google Analytics 4
//   1. Create a GA4 property → copy its Measurement ID ("G-XXXXXXXXXX").
//   2. Paste it into GA_MEASUREMENT_ID below.
// The loader is injected from this page, so it works even if you can't edit the
// app's index.html. To track the WHOLE app instead, move the standard gtag
// <script> snippet into index.html <head> and delete initGA() here.
// ─────────────────────────────────────────────────────────────────────────────
const GA_MEASUREMENT_ID = 'G-XXXXXXXXXX';                          // ← replace
const CANONICAL_URL = 'https://optionwheelpro.com/TraderStages';   // ← your real public URL

function initGA() {
  if (typeof window === 'undefined') return;
  if (!GA_MEASUREMENT_ID || GA_MEASUREMENT_ID.indexOf('XXXX') !== -1) return; // not configured yet
  if (window.__owpGaLoaded) return;
  window.__owpGaLoaded = true;
  const s = document.createElement('script');
  s.async = true;
  s.src = `https://www.googletagmanager.com/gtag/js?id=${GA_MEASUREMENT_ID}`;
  document.head.appendChild(s);
  window.dataLayer = window.dataLayer || [];
  window.gtag = window.gtag || function () { window.dataLayer.push(arguments); };
  window.gtag('js', new Date());
  window.gtag('config', GA_MEASUREMENT_ID, { send_page_view: false });
}

function track(name, params) {
  if (typeof window !== 'undefined' && typeof window.gtag === 'function') {
    window.gtag('event', name, params || {});
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// First-party visit log (backup metric alongside GA4).
// Writes ONE row per unique visitor per day to the base44 "PageVisit" entity, so
// distinct visitor_ids per visit_date = Unique Daily Visitors (see VisitStats page).
// NOTE: requires the PageVisit entity's *create* permission to allow public /
// anonymous writes, since this page is viewed logged-out. If base44 blocks
// anonymous entity writes, route this through a public backend function instead.
// ─────────────────────────────────────────────────────────────────────────────
async function logFirstPartyVisit() {
  if (typeof window === 'undefined') return;
  try {
    const today = new Date().toISOString().slice(0, 10); // YYYY-MM-DD (UTC)
    const flagKey = `owp_visit_logged_TraderStages_${today}`;
    if (localStorage.getItem(flagKey)) return;            // already counted this visitor today
    let vid = localStorage.getItem('owp_visitor_id');
    if (!vid) {
      vid = (window.crypto && window.crypto.randomUUID)
        ? window.crypto.randomUUID()
        : `v_${Date.now()}_${Math.random().toString(36).slice(2)}`;
      localStorage.setItem('owp_visitor_id', vid);
    }
    localStorage.setItem(flagKey, '1');                   // optimistic — avoids hammering on reload
    await base44.entities.PageVisit.create({
      page: 'TraderStages',
      visitor_id: vid,
      visit_date: today,
      referrer: document.referrer || 'direct',
    });
  } catch (e) {
    // Non-critical: never let analytics block the page.
    console.warn('PageVisit log skipped:', (e && e.message) || e);
  }
}

// ── SEO helpers (runtime-injected — see chat notes on adding static <head> tags) ──
function setMeta(attr, key, content) {
  let el = document.head.querySelector(`meta[${attr}="${key}"]`);
  if (!el) { el = document.createElement('meta'); el.setAttribute(attr, key); document.head.appendChild(el); }
  el.setAttribute('content', content);
}
function setLink(rel, href) {
  let el = document.head.querySelector(`link[rel="${rel}"]`);
  if (!el) { el = document.createElement('link'); el.setAttribute('rel', rel); document.head.appendChild(el); }
  el.setAttribute('href', href);
}
function injectJsonLd(id, data) {
  let el = document.getElementById(id);
  if (!el) { el = document.createElement('script'); el.type = 'application/ld+json'; el.id = id; document.head.appendChild(el); }
  el.textContent = JSON.stringify(data);
}

const FAQS = [
  {
    q: "What are the 7 stages of a trader?",
    a: "The seven stages are: 1) Blissful Ignorance, 2) The Awakening, 3) The Search, 4) Awareness, 5) The Rule Builder, 6) Consistent Execution, and 7) Unconscious Competence. They describe the psychological journey every trader walks on the way to lasting consistency."
  },
  {
    q: "How do I know which trading stage I'm in?",
    a: "Take the free 8-question assessment on this page. It places you using a 'weakest-link' method: because the stages are a sequential ladder that can't be skipped, you're anchored to the lowest stage where you still show a repeated, active struggle — not an average of your answers."
  },
  {
    q: "Which stage do most traders get stuck in or quit?",
    a: "Most traders quit during Stage 2 (The Awakening), right after their first painful loss, or get stuck for years in Stage 3 (The Search) — endlessly hunting for a better strategy instead of learning to execute the one they already have."
  },
  {
    q: "Is this based on Mark Douglas and Trading in the Zone?",
    a: "Yes. This stage framework is drawn from the trader-psychology teaching popularized by Mark Douglas, author of Trading in the Zone and The Disciplined Trader. The core idea: the strategy was never the problem — your psychology and discipline are."
  },
  {
    q: "How do I move from one stage to the next?",
    a: "Every transition is behavioral, not intellectual. You don't advance by acquiring more knowledge — you advance by changing one behavior at a time: writing down rules, tracking your daily rule-compliance, and repeating disciplined execution until it becomes automatic."
  },
];

// ─────────────────────────────────────────────────────────────────────────────
// Trader Stage Finder
// Based on "The 7 Stages Mark Douglas Said Every Trader Goes Through Before
// Finally Winning." Self-contained — no entities or API calls required.
// Accessible from the Beta Features dropdown.
// ─────────────────────────────────────────────────────────────────────────────

const STAGES = {
  1: {
    name: "Blissful Ignorance",
    tag: "“I can do this. How hard can it be?”",
    where: [
      "You’ve just discovered trading and something inside you lit up. You opened an account, funded it, and started placing trades on gut feeling and excitement.",
      "You may even be making money — but not because you know what you’re doing. The market is random enough that beginners win by accident. You have no concept of risk management, probability, or rules."
    ],
    trapH: "The trap",
    trap: "Those early wins are poison — they confirm the story “I have natural talent.” You’re a passenger on a roller coaster who thinks he’s driving. This stage ends the same way for everyone: a loss big enough to make you realize this is real money that can actually hurt you.",
    next: 2,
    nextLine: "Grow up before the inevitable big loss bankrupts you. The healthy move is to build survival habits now.",
    actions: [
      "Cap risk at 1–2% of your account per trade — today, before the big loss finds you.",
      "Accept in writing that your early wins were probably luck, not skill.",
      "Start a trade journal: log every entry, exit, and the real reason behind it.",
      "Learn the basics of probability and expectancy — one trade means nothing.",
      "Trade smaller. Right now, survival is the only goal."
    ],
    tonight: "Set a hard max-loss-per-trade rule and commit to never exceeding it."
  },
  2: {
    name: "The Awakening",
    tag: "“Wait — this can actually hurt me.”",
    where: [
      "You’ve been humbled by a real loss. The excitement is gone and in its place is fear, doubt, and confusion. Strategies that worked last week are failing this week.",
      "You feel stupid, like everyone else figured this out except you. This is the most emotionally difficult stage of the journey — and where the majority of traders quit forever."
    ],
    trapH: "What you need to hear",
    trap: "Nothing is wrong with you. This is the path. Every successful trader you admire sat exactly where you’re sitting and felt exactly what you feel. The only difference between those who make it and those who quit is the willingness to stay in the discomfort long enough to learn. You’re not failing — you’re waking up.",
    next: 3,
    nextLine: "Don’t quit. Survive the awakening and channel the desperation into focused learning instead of panic.",
    actions: [
      "Decide right now that you will not quit — commit to a timeline measured in months, not days.",
      "Cut your position size so you can survive long enough to actually learn.",
      "Reframe your losses as tuition, not failure.",
      "Pick ONE market and ONE strategy to study deeply — resist grabbing everything at once.",
      "Separate your self-worth from your account balance."
    ],
    tonight: "Write “I am not failing, I am waking up” and commit to staying in the game one more month."
  },
  3: {
    name: "The Search",
    tag: "“This is it. This is the one.” (again)",
    where: [
      "You’ve become a strategy collector — books, courses, YouTube, Discords, indicators, chart patterns. You’re hunting the holy grail: the one system that will finally make everything work.",
      "Each new strategy gives a rush of hope, works for a few days, then stops — and you feel betrayed, abandon it, and go looking for the next one. Traders can stay here for years."
    ],
    trapH: "The cruel irony",
    trap: "The strategy was never the problem. Many of the strategies you abandoned were perfectly good. Your inability to execute one consistently is the real problem. If your strategy has a defined edge and you’ve backtested it, it is already good enough. You don’t need a better strategy — you need the ability to execute the one you have.",
    next: 4,
    nextLine: "Stage 3 → 4 is not about finding a better strategy. It’s about realizing you don’t need one.",
    actions: [
      "Impose a strategy freeze — stop downloading, buying, or testing anything new.",
      "Choose ONE strategy with a defined edge and commit to it for a fixed sample (e.g. 100 trades).",
      "Backtest it until you genuinely trust the edge — then stop second-guessing it.",
      "For every losing trade, log whether the strategy failed or your execution failed. It’s almost always execution.",
      "Accept the hardest truth in trading: the problem is you, not the system."
    ],
    tonight: "Pick your one strategy and close every other system you’re currently juggling."
  },
  4: {
    name: "Awareness",
    tag: "“I know exactly what to do — so why can’t I do it?”",
    where: [
      "You’ve stopped searching — not because you found the perfect strategy, but because you finally realized the problem isn’t your system, it’s you. Most traders never reach this shift.",
      "You understand probability. You know no single trade matters and your edge only plays out over a large sample. You can explain all of it clearly… and yet you still move stops, cut winners early, skip valid setups, and revenge trade. You feel like two different people."
    ],
    trapH: "Why knowing isn’t enough",
    trap: "Understanding is a function of your rational mind; execution under pressure is a function of your emotional mind — and they operate independently. Knowing a loss is acceptable doesn’t make it feel acceptable. The gap between knowing and doing is the entire game. Your frustration is actually progress: you can only be frustrated because you’re now aware of the gap, and awareness always precedes change.",
    next: 5,
    nextLine: "Stage 4 → 5 is not about understanding more psychology. It’s about writing your rules down and committing to follow them.",
    actions: [
      "Stop trying to think your way out of a behavioral problem — build structure instead.",
      "Write non-negotiable rules for: risk per trade, valid setups, stop placement, target, when to stop trading, and what to do after a win and after a loss.",
      "Make them rigid and specific — rules, not guidelines or suggestions.",
      "Pre-commit: decide every execution choice before the market opens.",
      "Reduce in-the-moment discretion to near zero while you build discipline."
    ],
    tonight: "Write your full rulebook on a single page and sign it."
  },
  5: {
    name: "The Rule Builder",
    tag: "“Having rules is easy. Following them is hard.”",
    where: [
      "You’ve done what most traders never do: codified your knowledge into rigid, written, non-negotiable rules that govern every part of your trading.",
      "But you follow them inconsistently — disciplined some days, falling apart others. You might follow them all week, then blow up on one bad afternoon. Every broken rule lands as a sting of self-disappointment."
    ],
    trapH: "Why the inconsistency is good news",
    trap: "You used to break rules without even noticing. Now you break them and it bothers you — which means the rules have become part of your identity. That sting of self-disappointment is your brain building a negative association with rule-breaking, and over time it becomes strong enough to override the impulse in real time. The discomfort is the very thing that will stop you.",
    next: 6,
    nextLine: "Stage 5 → 6 is not about willpower. It’s about tracking your compliance until discipline becomes a habit.",
    actions: [
      "Score yourself every day on ONE metric — “Did I follow my rules?” — as a number out of 10.",
      "Track that compliance score over time and watch it climb week over week, even when your balance doesn’t.",
      "Redefine a “good day” as a COMPLIANT day, not a profitable one.",
      "Review every rule break: what was the trigger, and what will you do differently next time?",
      "Treat following the rules as non-negotiable — this is the threshold most traders never cross."
    ],
    tonight: "Create a compliance tracker and give today an honest score out of 10."
  },
  6: {
    name: "Consistent Execution",
    tag: "“Where’s the thrill? …Is this really it?”",
    where: [
      "You follow your rules consistently — not perfectly, but most days you execute the plan, follow your criteria, and accept most losses without drama. The occasional slip is now the exception, not the norm.",
      "Your account reflects it: not explosive growth, but steady, boring, incremental progress. And here’s the paradox — instead of feeling confident and validated, you feel almost nothing. You feel bored."
    ],
    trapH: "That boredom is the goal",
    trap: "The thrill and the rush were never signs of good trading — they were signs of gambling, your emotional brain hijacking your decisions. The absence of emotion isn’t emptiness; it’s freedom: the freedom to execute without your survival instincts screaming at you to do something different. If trading feels boring, you are doing it right.",
    next: 7,
    nextLine: "Stage 6 → 7 is repetition. Enough disciplined reps and execution stops being a battle and becomes automatic.",
    actions: [
      "Keep executing — sheer volume of disciplined reps is what internalizes the behavior.",
      "Stop celebrating wins and mourning losses; treat every outcome identically.",
      "Let the routine become so automatic you no longer have to talk yourself into discipline.",
      "Protect the boredom — resist the urge to add complexity or “spice it up.”",
      "Trust that your results now come from removing yourself, not from a better strategy."
    ],
    tonight: "Notice the boredom tonight and label it for what it is: proof you’ve arrived."
  },
  7: {
    name: "Unconscious Competence",
    tag: "“My rules aren’t something I follow — they’re something I am.”",
    where: [
      "You don’t think about following your rules anymore — you just follow them, the way you don’t think about how to drive a car. The mechanics are internalized so deeply they’re automatic.",
      "Execution is no longer a battle between your rational and emotional mind; the two have merged. You recognize setups without conscious analysis, size positions without anxiety, place trades without hesitation, and accept losses without narrative. Discipline is your default state."
    ],
    trapH: "What you’ve actually achieved",
    trap: "Your results improved not because you found a better strategy or the market started cooperating, but because you removed every psychological obstacle between you and your edge. You got out of your own way. You’ve mastered yourself — and that quiet, boring, unshakable discipline is worth more than any single trade, month, or year. Nobody can take it from you.",
    next: null,
    nextLine: "This is mastery. There’s no next stage to chase — the work now is protecting what you’ve built.",
    actions: [
      "Review your rules periodically so they don’t silently drift over time.",
      "Watch for complacency and “creativity creep” that quietly re-introduces ego.",
      "Scale your size only as fast as your psychology stays automatic.",
      "Teach or journal your process — it deepens the internalization.",
      "Remember: not the market, not a losing streak, not anyone can take this mastery from you. Keep walking."
    ],
    tonight: "Write down the discipline that got you here, so you never drift away from it."
  }
};

// Each option maps to the stage it signals.
const QUESTIONS = [
  {
    q: "Which sentence best describes how trading feels to you right now?",
    o: [
      ["Excited and confident — I’m sure this is my ticket to financial freedom.", 1],
      ["Shaken and fearful — a real loss humbled me and the thrill is gone.", 2],
      ["Restless and hopeful — I’m always hunting for the next, better system.", 3],
      ["Frustrated — I know exactly what to do but can’t make myself do it.", 4],
      ["Determined — I’m grinding to follow my rules, day by day.", 5],
      ["Calm, almost bored — I just execute and move on.", 6],
      ["Neutral and effortless — discipline is just who I am now.", 7],
    ]
  },
  {
    q: "What is your relationship with trading strategies?",
    o: [
      ["I don’t really have one — I trade on gut feeling and excitement.", 1],
      ["My strategy stopped working and now I feel completely lost.", 2],
      ["I switch strategies every few days or weeks, chasing the holy grail.", 3],
      ["I have one I trust; my whole problem is following it.", 4],
      ["I’ve codified my approach into rigid written rules.", 5],
      ["I follow one defined plan consistently, with only rare slips.", 6],
      ["I recognize my setups and execute without conscious analysis.", 7],
    ]
  },
  {
    q: "Do you have written trading rules — and do you follow them?",
    o: [
      ["Rules? I just place trades.", 1],
      ["I had some, but the losses blew right through them.", 2],
      ["My rules keep changing every time I adopt a new system.", 3],
      ["I know what my rules should be but haven’t actually committed them.", 4],
      ["I have rigid written rules, but I break them fairly often.", 5],
      ["I follow my written rules most days.", 6],
      ["My rules are automatic — following them takes no effort.", 7],
    ]
  },
  {
    q: "How do you typically react to a losing trade?",
    o: [
      ["I shrug it off — I barely register the risk.", 1],
      ["I’m devastated and tempted to quit altogether.", 2],
      ["I blame the strategy and go looking for a new one.", 3],
      ["I know it’s fine, yet I revenge-trade or move my stop anyway.", 4],
      ["It stings most when I realize I broke one of my own rules.", 5],
      ["I accept it and move on — no drama.", 6],
      ["I accept it without any story or emotion at all.", 7],
    ]
  },
  {
    q: "What makes a trading day a “good day” for you?",
    o: [
      ["A day I made money and felt the rush.", 1],
      ["A day I simply didn’t lose more.", 2],
      ["A day I discovered a promising new setup or system.", 3],
      ["A day I understood the market a little better.", 4],
      ["A day I followed my rules — I’m starting to think this way.", 5],
      ["A compliant day — whether I made money is almost irrelevant.", 6],
      ["Every day feels the same; I just execute.", 7],
    ]
  },
  {
    q: "How much of your trading is driven by emotion vs. process?",
    o: [
      ["Pure emotion — excitement and gut feeling run the show.", 1],
      ["Emotion is overwhelming me — fear and doubt dominate.", 2],
      ["Hope drives me — each new system feels like salvation.", 3],
      ["I see my emotions hijack me even though I know better.", 4],
      ["I’m actively fighting my emotions with structure and rules.", 5],
      ["Emotion is mostly quiet — it rarely affects my decisions.", 6],
      ["There’s no battle left — rational and emotional mind have merged.", 7],
    ]
  },
  {
    q: "Do you track anything about your own behavior (not just P&L)?",
    o: [
      ["No — I only watch the money going up or down.", 1],
      ["No — I’m too overwhelmed to track anything right now.", 3],
      ["I track strategies’ results, but not my own discipline.", 3],
      ["I’ve realized I should track my behavior but haven’t started.", 4],
      ["I’m starting to score my rule-compliance each day.", 5],
      ["Yes — I score my compliance daily and it’s steadily climbing.", 6],
      ["I don’t need to — compliance is automatic and near-perfect.", 7],
    ]
  },
  {
    q: "Be ruthlessly honest: where do you sense you actually are?",
    o: [
      ["Brand new and certain I’ll crush it.", 1],
      ["Recently humbled and questioning everything.", 2],
      ["Stuck cycling through strategies, never sticking with one.", 3],
      ["Aware it’s me, not the system — but unable to execute.", 4],
      ["Building discipline with rules I follow inconsistently.", 5],
      ["Consistent, disciplined, and a little bored by it.", 6],
      ["Self-mastered — discipline is simply my default.", 7],
    ]
  },
];

// Weakest-link scoring: the 7 stages are a strict, non-skippable ladder, so we
// do NOT average mixed signals. We anchor to the lowest stage where the trader
// still shows a *repeated* (>=2 answers) active struggle. A single stray answer
// is treated as self-report noise. An unresolved earlier struggle is a binding
// constraint that caps your real stage regardless of higher-stage habits.
function determineStage(answers) {
  const tally = { 1: 0, 2: 0, 3: 0, 4: 0, 5: 0, 6: 0, 7: 0 };
  answers.forEach((ai, qi) => { tally[QUESTIONS[qi].o[ai][1]]++; });

  const SUPPORT = 2;
  const supported = [];
  const present = [];
  for (let s = 1; s <= 7; s++) {
    if (tally[s] > 0) present.push(s);
    if (tally[s] >= SUPPORT) supported.push(s);
  }

  let stageNum;
  if (supported.length) {
    stageNum = supported[0]; // lowest supported = the binding constraint
  } else {
    const arr = answers.map((ai, qi) => QUESTIONS[qi].o[ai][1]).sort((a, b) => a - b);
    stageNum = arr[Math.floor(arr.length / 2)];
  }

  const lo = present[0], hi = present[present.length - 1];
  const higher = supported.filter(s => s > stageNum);
  const mixed = supported.length > 1 || (hi - lo) >= 2;
  const wide = (hi - lo) >= 3;

  return { stageNum, diag: { tally, mixed, wide, higher, lo, hi } };
}

export default function TraderStages() {
  const [screen, setScreen] = useState('intro'); // 'intro' | 'quiz' | 'result'
  const [cur, setCur] = useState(0);
  const [answers, setAnswers] = useState(Array(QUESTIONS.length).fill(null));
  const [result, setResult] = useState(null);

  // Analytics + SEO: fire once when the public page loads.
  useEffect(() => {
    initGA();
    track('page_view', {
      page_title: 'Trader Stage Finder',
      page_location: CANONICAL_URL,
      page_path: '/TraderStages',
    });
    logFirstPartyVisit();

    const prevTitle = document.title;
    document.title = 'What Stage Trader Are You? — The 7 Stages of a Trader Quiz (Mark Douglas)';
    setMeta('name', 'description', 'Free quiz based on Mark Douglas’s 7 stages of a trader. Find which stage you’re in — from Blissful Ignorance to Unconscious Competence — and get the one behavioral change to reach the next stage. No login required.');
    setMeta('name', 'keywords', 'Mark Douglas, 7 stages of a trader, trading psychology, Trading in the Zone, which trading stage am I in, trader stages quiz, trader development stages');
    setMeta('name', 'robots', 'index, follow');
    setLink('canonical', CANONICAL_URL);
    setMeta('property', 'og:type', 'website');
    setMeta('property', 'og:title', 'The 7 Stages of a Trader — Which Stage Are You In?');
    setMeta('property', 'og:description', 'A free quiz based on Mark Douglas’s 7 stages of trader psychology. Find your stage and the one change that moves you to the next.');
    setMeta('property', 'og:url', CANONICAL_URL);
    setMeta('name', 'twitter:card', 'summary_large_image');
    setMeta('name', 'twitter:title', 'The 7 Stages of a Trader — Which Stage Are You In?');
    setMeta('name', 'twitter:description', 'Free trader-psychology quiz based on Mark Douglas. Find your stage in ~2 minutes.');

    injectJsonLd('owp-jsonld-faq', {
      '@context': 'https://schema.org',
      '@type': 'FAQPage',
      mainEntity: FAQS.map(f => ({
        '@type': 'Question',
        name: f.q,
        acceptedAnswer: { '@type': 'Answer', text: f.a },
      })),
    });
    injectJsonLd('owp-jsonld-app', {
      '@context': 'https://schema.org',
      '@type': 'WebApplication',
      name: 'Trader Stage Finder',
      url: CANONICAL_URL,
      applicationCategory: 'FinanceApplication',
      operatingSystem: 'Web',
      offers: { '@type': 'Offer', price: '0', priceCurrency: 'USD' },
      description: 'Free quiz based on Mark Douglas’s 7 stages of a trader. Find which trading psychology stage you are in and how to reach the next.',
    });

    return () => { document.title = prevTitle; };
  }, []);

  const scrollTop = () => window.scrollTo({ top: 0, behavior: 'smooth' });

  const start = () => { track('quiz_start'); setCur(0); setScreen('quiz'); scrollTop(); };

  const choose = (i) => {
    const copy = [...answers];
    copy[cur] = i;
    setAnswers(copy);
  };

  const next = () => {
    if (answers[cur] === null) return;
    if (cur < QUESTIONS.length - 1) {
      setCur(cur + 1);
      scrollTop();
    } else {
      const r = determineStage(answers);
      setResult(r);
      track('quiz_complete', { stage: r.stageNum, stage_name: STAGES[r.stageNum].name });
      setScreen('result');
      scrollTop();
    }
  };

  const prev = () => { if (cur > 0) { setCur(cur - 1); scrollTop(); } };

  const restart = () => {
    track('quiz_restart');
    setAnswers(Array(QUESTIONS.length).fill(null));
    setCur(0);
    setResult(null);
    setScreen('intro');
    scrollTop();
  };

  // ── INTRO ──────────────────────────────────────────────────────────────────
  if (screen === 'intro') {
    return (
      <div className="min-h-screen bg-background">
        <div className="max-w-3xl mx-auto px-6 py-12">
          <div className="inline-flex items-center gap-2 text-xs font-semibold tracking-widest uppercase text-amber-600 dark:text-amber-400 border border-amber-300 dark:border-amber-500/40 bg-amber-50 dark:bg-amber-500/10 rounded-full px-3 py-1.5">
            <FlaskConical className="w-3.5 h-3.5" />
            Beta · Trader Psychology
          </div>

          <h1 className="mt-5 text-4xl md:text-5xl font-bold tracking-tight text-slate-900 dark:text-slate-50 leading-tight">
            Which of the{' '}
            <span className="text-transparent bg-clip-text bg-gradient-to-r from-emerald-500 to-indigo-500">7 stages</span>{' '}
            are you actually in?
          </h1>

          <p className="mt-4 text-lg text-slate-600 dark:text-slate-400 leading-relaxed">
            Every trader who reaches lasting consistency walks the same road. The frustration you
            feel comes from not knowing where you are on it. Answer honestly — not where you{' '}
            <em>want</em> to be, where you <em>actually</em> are — and this finder will place you,
            then hand you the one behavioral change that moves you to the next stage.
          </p>

          <Card className="mt-8 border-slate-200 dark:border-slate-700 shadow-lg">
            <CardContent className="pt-6">
              <div className="text-lg font-semibold text-slate-800 dark:text-slate-100">
                8 honest questions · ~2 minutes
              </div>
              <div className="mt-3 flex flex-wrap gap-x-6 gap-y-2 text-sm text-slate-500 dark:text-slate-400">
                <span><b className="text-slate-700 dark:text-slate-200">Diagnoses</b> your current stage</span>
                <span><b className="text-slate-700 dark:text-slate-200">Explains</b> what’s happening psychologically</span>
                <span><b className="text-slate-700 dark:text-slate-200">Gives</b> concrete next-stage action items</span>
              </div>
              <Button
                onClick={start}
                className="mt-6 h-12 px-7 text-base font-semibold bg-gradient-to-r from-emerald-500 to-emerald-600 hover:from-emerald-600 hover:to-emerald-700 text-white"
              >
                Find my stage <ArrowRight className="w-5 h-5 ml-2" />
              </Button>
            </CardContent>
          </Card>

          <p className="mt-7 text-center text-xs text-slate-400 dark:text-slate-500 leading-relaxed">
            Based on <em>“The 7 Stages Mark Douglas Said Every Trader Goes Through Before Finally Winning.”</em>
            <br />Your ego will resist the honest answer. Let it resist — the truth is more useful than comfort.
          </p>

          {/* Crawlable SEO content — visible on the public landing view */}
          <section className="mt-12 border-t border-slate-200 dark:border-slate-800 pt-8">
            <h2 className="text-2xl font-bold text-slate-900 dark:text-slate-50">
              The 7 stages of a trader, explained
            </h2>
            <p className="mt-3 text-slate-600 dark:text-slate-400 leading-relaxed">
              Popularized by trading-psychology author <strong>Mark Douglas</strong>{' '}
              (<em>Trading in the Zone</em>, <em>The Disciplined Trader</em>), this framework maps the
              psychological road every trader walks toward lasting consistency. Whatever your strategy or
              account size, the progression is the same — and knowing where you are dissolves the
              frustration of feeling stuck. The seven stages are:
            </p>
            <ol className="mt-4 grid sm:grid-cols-2 gap-x-6 gap-y-2 text-slate-700 dark:text-slate-300 list-decimal list-inside">
              {[1, 2, 3, 4, 5, 6, 7].map(i => (
                <li key={i}>
                  <span className="font-semibold">{STAGES[i].name}</span>
                  <span className="text-slate-500 dark:text-slate-400"> — {STAGES[i].tag.replace(/[“”]/g, '')}</span>
                </li>
              ))}
            </ol>

            <h2 className="mt-10 text-2xl font-bold text-slate-900 dark:text-slate-50">
              Frequently asked questions
            </h2>
            <div className="mt-4 space-y-3">
              {FAQS.map((f, i) => (
                <details
                  key={i}
                  className="group rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900/40 px-4 py-3"
                >
                  <summary className="cursor-pointer font-semibold text-slate-800 dark:text-slate-100 marker:text-slate-400">
                    {f.q}
                  </summary>
                  <p className="mt-2 text-slate-600 dark:text-slate-400 leading-relaxed">{f.a}</p>
                </details>
              ))}
            </div>
          </section>
        </div>
      </div>
    );
  }

  // ── QUIZ ───────────────────────────────────────────────────────────────────
  if (screen === 'quiz') {
    const Q = QUESTIONS[cur];
    const pct = (cur / QUESTIONS.length) * 100;
    const isLast = cur === QUESTIONS.length - 1;
    return (
      <div className="min-h-screen bg-background">
        <div className="max-w-3xl mx-auto px-6 py-12">
          <div className="text-sm text-slate-500 dark:text-slate-400 mb-1.5 tracking-wide">
            Question {cur + 1} of {QUESTIONS.length}
          </div>
          <div className="h-1.5 w-full bg-slate-200 dark:bg-slate-800 rounded-full overflow-hidden mb-6">
            <div
              className="h-full bg-gradient-to-r from-indigo-500 to-emerald-500 rounded-full transition-all duration-300"
              style={{ width: `${pct}%` }}
            />
          </div>

          <Card className="border-slate-200 dark:border-slate-700 shadow-lg">
            <CardContent className="pt-6">
              <div className="text-xl md:text-2xl font-semibold text-slate-900 dark:text-slate-50 mb-6 leading-snug">
                {Q.q}
              </div>

              <div className="flex flex-col gap-3">
                {Q.o.map((opt, i) => {
                  const sel = answers[cur] === i;
                  return (
                    <button
                      key={i}
                      onClick={() => choose(i)}
                      className={`flex gap-3 items-start text-left w-full rounded-xl px-4 py-3.5 border transition-colors
                        ${sel
                          ? 'border-emerald-500 bg-emerald-50 dark:bg-emerald-500/10 ring-1 ring-emerald-500'
                          : 'border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900/40 hover:border-indigo-400 dark:hover:border-indigo-500'}`}
                    >
                      <span className={`flex-none mt-0.5 w-5 h-5 rounded-full border-2 flex items-center justify-center
                        ${sel ? 'border-emerald-500 bg-emerald-500' : 'border-slate-400 dark:border-slate-500'}`}>
                        {sel && <span className="w-2 h-2 rounded-full bg-white" />}
                      </span>
                      <span className="text-slate-700 dark:text-slate-200">{opt[0]}</span>
                    </button>
                  );
                })}
              </div>

              <div className="mt-6 flex justify-between items-center">
                <Button
                  variant="outline"
                  onClick={prev}
                  className={cur === 0 ? 'invisible' : ''}
                >
                  <ArrowLeft className="w-4 h-4 mr-2" /> Back
                </Button>
                <Button
                  onClick={next}
                  disabled={answers[cur] === null}
                  className="bg-gradient-to-r from-emerald-500 to-emerald-600 hover:from-emerald-600 hover:to-emerald-700 text-white font-semibold"
                >
                  {isLast ? 'See my stage' : 'Next'} <ArrowRight className="w-4 h-4 ml-2" />
                </Button>
              </div>
            </CardContent>
          </Card>

          <p className="mt-6 text-center text-xs text-slate-400 dark:text-slate-500">
            Place yourself where you are, not where you wish you were.
          </p>
        </div>
      </div>
    );
  }

  // ── RESULT ─────────────────────────────────────────────────────────────────
  const { stageNum, diag } = result;
  const S = STAGES[stageNum];

  return (
    <div className="min-h-screen bg-background">
      <div className="max-w-3xl mx-auto px-6 py-12">
        <Card className="border-slate-200 dark:border-slate-700 shadow-lg">
          <CardContent className="pt-6">
            <div className="text-xs tracking-widest uppercase text-slate-500 dark:text-slate-400">
              Your stage — {stageNum} of 7
            </div>
            <div className="mt-1.5 text-3xl font-bold text-slate-900 dark:text-slate-50">
              <span className="text-emerald-500">Stage {stageNum}.</span> {S.name}
            </div>
            <div className="mt-1 text-slate-500 dark:text-slate-400 italic">{S.tag}</div>

            {/* Ladder */}
            <div className="mt-6">
              {[1, 2, 3, 4, 5, 6, 7].map((i, idx) => {
                const done = i < stageNum;
                const isCurrent = i === stageNum;
                return (
                  <div key={i} className="relative flex items-center gap-3.5 py-2">
                    {idx < 6 && (
                      <span className="absolute left-[14px] top-[30px] w-0.5 h-[calc(100%-4px)] bg-slate-200 dark:bg-slate-700" />
                    )}
                    <span className={`relative z-10 flex-none w-7 h-7 rounded-full border-2 flex items-center justify-center text-xs font-bold
                      ${isCurrent
                        ? 'border-amber-400 bg-amber-400 text-amber-950 ring-4 ring-amber-400/20'
                        : done
                          ? 'border-emerald-500 text-emerald-500 bg-white dark:bg-slate-900'
                          : 'border-slate-300 dark:border-slate-600 text-slate-400 dark:text-slate-500 bg-white dark:bg-slate-900'}`}>
                      {done ? <Check className="w-3.5 h-3.5" /> : i}
                    </span>
                    <span className={`text-sm
                      ${isCurrent
                        ? 'text-amber-600 dark:text-amber-400 font-semibold'
                        : done ? 'text-slate-800 dark:text-slate-200' : 'text-slate-400 dark:text-slate-500'}`}>
                      Stage {i} · {STAGES[i].name}
                    </span>
                  </div>
                );
              })}
            </div>

            {/* Why this stage (mixed answers) */}
            {diag.mixed && (
              <>
                <SectionH color="indigo">Why Stage {stageNum}? — your answers were mixed</SectionH>
                <div className="rounded-xl border border-slate-200 dark:border-slate-700 bg-indigo-50/60 dark:bg-indigo-500/5 border-l-4 !border-l-indigo-500 p-4 text-slate-700 dark:text-slate-300">
                  <p>
                    Your responses spanned{' '}
                    {diag.lo === diag.hi ? `Stage ${diag.lo}` : `Stage ${diag.lo} through Stage ${diag.hi}`}.
                    This path is sequential and can’t be skipped, so we don’t average mixed answers —
                    we anchor you to the{' '}
                    <b>lowest stage where you still show a repeated, active struggle</b>. An unresolved
                    earlier struggle is a binding constraint: it sets your real stage no matter how many
                    advanced habits you’ve also built.
                    {diag.higher.length > 0 && (
                      <>
                        {' '}You also showed genuine signals of{' '}
                        <b>{diag.higher.map(s => `Stage ${s} · ${STAGES[s].name}`).join(' and ')}</b>{' '}
                        — that’s real progress, or a glimpse of where you’re heading. But those higher
                        habits only become your <em>default</em> once the Stage {stageNum} struggle is
                        resolved; until then, the earlier struggle is what caps you.
                      </>
                    )}
                    {diag.wide && (
                      <span className="text-amber-600 dark:text-amber-400">
                        {' '}Your answers were unusually spread out — if that doesn’t feel right, retake
                        it and answer for what you <em>actually</em> do, not what you know you{' '}
                        <em>should</em> do.
                      </span>
                    )}
                  </p>
                </div>
              </>
            )}

            {/* Where you are */}
            <SectionH color="indigo">Where you are</SectionH>
            <div className="rounded-xl border border-slate-200 dark:border-slate-700 border-l-4 !border-l-emerald-500 p-4 space-y-2.5 text-slate-700 dark:text-slate-300">
              {S.where.map((p, i) => <p key={i}>{p}</p>)}
            </div>

            {/* Trap / insight */}
            <SectionH color="indigo">{S.trapH}</SectionH>
            <div className="rounded-xl border border-slate-200 dark:border-slate-700 border-l-4 !border-l-amber-500 p-4 text-slate-700 dark:text-slate-300">
              <p>{S.trap}</p>
            </div>

            {/* Next stage / actions */}
            <SectionH color="indigo">
              {S.next ? 'Your road to the next stage' : 'Protecting your mastery'}
            </SectionH>
            <div className="rounded-xl border border-indigo-200 dark:border-indigo-500/30 bg-gradient-to-b from-indigo-50/70 to-transparent dark:from-indigo-500/10 p-5">
              <div className="text-sm text-slate-500 dark:text-slate-400">
                {S.next
                  ? <>Next up → <b className="text-indigo-600 dark:text-indigo-400">Stage {S.next} · {STAGES[S.next].name}</b></>
                  : <b className="text-indigo-600 dark:text-indigo-400">You’ve reached the final stage.</b>}
              </div>
              <p className="mt-2 text-slate-600 dark:text-slate-300">{S.nextLine}</p>
              <ul className="mt-4 flex flex-col gap-3">
                {S.actions.map((a, i) => (
                  <li key={i} className="flex gap-3 items-start text-slate-700 dark:text-slate-200">
                    <span className="flex-none mt-0.5 w-5 h-5 rounded-md bg-emerald-100 dark:bg-emerald-500/15 border border-emerald-400 text-emerald-600 dark:text-emerald-400 flex items-center justify-center">
                      <Check className="w-3.5 h-3.5" />
                    </span>
                    <span>{a}</span>
                  </li>
                ))}
              </ul>
            </div>

            {/* One thing tonight */}
            <div className="mt-5 rounded-xl border border-amber-200 dark:border-amber-500/30 bg-gradient-to-r from-amber-50 to-transparent dark:from-amber-500/10 p-4">
              <div className="text-xs font-bold tracking-widest uppercase text-amber-600 dark:text-amber-400">
                Do this one thing tonight
              </div>
              <p className="mt-1.5 text-slate-700 dark:text-amber-50/90">{S.tonight}</p>
            </div>

            <p className="mt-6 text-center text-slate-500 dark:text-slate-400 italic">
              “You don’t move forward by acquiring more knowledge. You move forward by changing your behavior.”
            </p>
          </CardContent>
        </Card>

        <div className="mt-6 flex flex-wrap justify-center gap-3">
          <Button variant="outline" onClick={restart}>
            <RotateCcw className="w-4 h-4 mr-2" /> Retake the assessment
          </Button>
          <Button
            onClick={() => window.print()}
            className="bg-gradient-to-r from-emerald-500 to-emerald-600 hover:from-emerald-600 hover:to-emerald-700 text-white"
          >
            <Printer className="w-4 h-4 mr-2" /> Save / print my result
          </Button>
        </div>

        <p className="mt-6 text-center text-xs text-slate-400 dark:text-slate-500">
          You are not stuck. You never were. You just didn’t have the map. Now you do — keep walking.
        </p>
      </div>
    </div>
  );
}

// Small reusable section heading
function SectionH({ children }) {
  return (
    <div className="mt-7 mb-2.5 text-xs font-bold tracking-widest uppercase text-indigo-500 dark:text-indigo-400 flex items-center gap-2">
      <TrendingUp className="w-3.5 h-3.5" />
      {children}
    </div>
  );
}
