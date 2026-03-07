import Link from "next/link";

export default function Home() {
  return (
    <div className="flex min-h-screen flex-col bg-white dark:bg-zinc-950 text-zinc-900 dark:text-zinc-50">
      <header className="flex h-16 items-center border-b border-zinc-200 dark:border-zinc-800 px-6 lg:px-12 sticky top-0 bg-white/80 dark:bg-zinc-950/80 backdrop-blur-sm z-10">
        <div className="flex items-center gap-2 font-bold text-xl">
          <div className="h-8 w-8 rounded bg-blue-600 flex items-center justify-center text-white font-heading">
            P
          </div>
          <span className="font-heading">PromptDash</span>
        </div>
        <nav className="ml-auto flex gap-6 text-sm font-medium text-zinc-600 dark:text-zinc-400">
          <Link href="#" className="hover:text-blue-600 transition-colors">Documentation</Link>
          <Link href="#" className="hover:text-blue-600 transition-colors">Settings</Link>
        </nav>
      </header>

      <main className="flex-1 px-6 py-16 lg:px-12">
        <section className="mx-auto max-w-4xl text-center space-y-8 animate-in fade-in slide-in-from-bottom-4 duration-700">
          <div className="space-y-4">
            <h1 className="text-5xl font-extrabold tracking-tight lg:text-6xl text-zinc-900 dark:text-white font-heading">
              Build Your Own <span className="text-blue-600">Dashboard</span>
            </h1>
            <p className="text-xl text-zinc-500 dark:text-zinc-400 max-w-2xl mx-auto leading-relaxed">
              Privacy-first analytics powered by local SLMs. <br className="hidden sm:inline" />
              Generate insights instantly without your data leaving your device.
            </p>
          </div>
          
          <div className="flex flex-col sm:flex-row items-center justify-center gap-4 pt-4">
             <button className="h-12 px-8 rounded-full bg-blue-600 text-white font-medium hover:bg-blue-700 transition-all shadow-lg hover:shadow-blue-500/25 active:scale-95">
               Generate New Dashboard
             </button>
             <button className="h-12 px-8 rounded-full border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 hover:bg-zinc-50 dark:hover:bg-zinc-800 transition-all active:scale-95">
               View Saved Reports
             </button>
          </div>
        </section>

        <section className="mt-24 mx-auto max-w-3xl">
           <div className="rounded-2xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900/50 shadow-xl overflow-hidden backdrop-blur-sm">
             <div className="p-1 bg-zinc-100 dark:bg-zinc-800/50 border-b border-zinc-200 dark:border-zinc-800 flex items-center gap-2 px-4 py-2">
               <div className="w-3 h-3 rounded-full bg-red-500/20 border border-red-500/50"></div>
               <div className="w-3 h-3 rounded-full bg-yellow-500/20 border border-yellow-500/50"></div>
               <div className="w-3 h-3 rounded-full bg-green-500/20 border border-green-500/50"></div>
               <span className="ml-2 text-xs font-mono text-zinc-400">prompt-terminal</span>
             </div>
             
             <div className="p-8 space-y-6">
               <div className="space-y-2">
                 <h2 className="text-2xl font-semibold">Ask your data</h2>
                 <p className="text-sm text-zinc-500">Describe the visualization you need. The SLM will handle the rest.</p>
               </div>
               
               <div className="relative">
                 <textarea 
                   placeholder="e.g., Create a line chart showing revenue growth over the last 12 months, highlighting Q4 peaks..."
                   className="w-full min-h-[160px] rounded-xl border border-zinc-200 dark:border-zinc-700 bg-zinc-50 dark:bg-zinc-950/50 px-4 py-4 text-base shadow-inner placeholder:text-zinc-400 focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-all resize-none"
                 />
                 <div className="absolute bottom-4 right-4 flex gap-2">
                   <button className="h-9 px-4 rounded-lg bg-zinc-900 dark:bg-white text-white dark:text-zinc-900 text-sm font-medium hover:opacity-90 transition-opacity flex items-center gap-2 shadow-sm">
                     <span>Generate</span>
                     <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M5 12h14"/><path d="m12 5 7 7-7 7"/></svg>
                   </button>
                 </div>
               </div>

               <div className="flex gap-2 overflow-x-auto pb-2 scrollbar-hide">
                 <span className="text-xs font-medium text-zinc-400 uppercase tracking-wider shrink-0 py-1">Try:</span>
                 {["Sales vs Target Q1", "Customer Churn Analysis", "Website Traffic Heatmap"].map((suggestion) => (
                   <button key={suggestion} className="px-3 py-1 text-xs rounded-full bg-zinc-100 dark:bg-zinc-800 text-zinc-600 dark:text-zinc-300 hover:bg-zinc-200 dark:hover:bg-zinc-700 transition-colors whitespace-nowrap">
                     {suggestion}
                   </button>
                 ))}
               </div>
             </div>
           </div>
        </section>

        <section className="mt-24 grid grid-cols-1 md:grid-cols-3 gap-8 max-w-6xl mx-auto">
           {[
             { title: "Local Processing", desc: "Data never leaves your machine. Full GDPR compliance out of the box.", icon: "🔒" },
             { title: "SLM Intelligence", desc: "Powered by Qwen 3 8B, optimized for efficient local graph generation.", icon: "🧠" },
             { title: "Instant Export", desc: "Share interactive HTML reports or static images with one click.", icon: "📤" }
           ].map((feature, i) => (
             <div key={i} className="p-6 rounded-xl border border-zinc-100 dark:border-zinc-800 bg-zinc-50/50 dark:bg-zinc-900/20 hover:bg-white dark:hover:bg-zinc-900 transition-colors">
               <div className="text-3xl mb-4">{feature.icon}</div>
               <h3 className="font-semibold text-lg mb-2">{feature.title}</h3>
               <p className="text-zinc-500 text-sm leading-relaxed">{feature.desc}</p>
             </div>
           ))}
        </section>
      </main>
      
      <footer className="py-8 text-center text-sm text-zinc-500 dark:text-zinc-400 border-t border-zinc-100 dark:border-zinc-800 mt-12">
        <p>&copy; {new Date().getFullYear()} PromptDash. Powered by Qwen 3 8B & LangGraph.</p>
      </footer>
    </div>
  );
}
