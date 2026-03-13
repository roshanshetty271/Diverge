import { useNavigate } from "react-router-dom";
import { TEMPLATES } from "../utils/constants";
import type { TemplateOption } from "../types";

export default function Templates() {
  const navigate = useNavigate();

  const handleSelect = (template: TemplateOption | "custom") => {
    if (template === "custom") {
      navigate("/intake", { state: { pathA: "", pathB: "", templateId: "custom" } });
    } else {
      navigate("/intake", { state: { pathA: template.pathA, pathB: template.pathB, templateId: template.id } });
    }
  };

  const getImageUrl = (id: string) => {
    switch (id) {
      case "career": return "https://lh3.googleusercontent.com/aida-public/AB6AXuDxrsyhoOzJlDs10i_-Rbtihc8HjxFBxkuR1ttWUBO--41C6gpxQh0Q6Lh38hbjm840YKSH9F6-acA69FkObPPh6_4ac96oqQ47R0E8gC3Dt1wRZRW_zZ3aQUZkYP03_GhxTOKoGzdlwTnlDeabsheB_xLaf26SPSzkjftUswrgyLpNsoHZCwK3ume2MW4HuTJ88TBiAjspRlJgK0virZWn8_gwpunnsdlci-J8GC4okabEN9RBARzH9CKfFtoV1XPI8UpvloxQudE";
      case "city": return "https://lh3.googleusercontent.com/aida-public/AB6AXuAY3c1pw3zuJl0QwfLHYVb_scK5Y4LIaHZOXZ3MCwTbTBMNIGlyp1PgTwj21OH9uDuKM3i_nAxfVsSFM-vlAm1iMSKSjU2QtNbYlHJrt-o4KbwK8jPMIp5TEjJXhAkvR7pbioMkiC7gcQKFimm-1BIr1rTLNavq3H41mnp5TtXvrTaojER3iRNU3ebyVzdLU07nlvnQB3omO8wDhWFUJGg_bv-96INumR_hjylCdg6qcAqGeFEnhxJ4rKWeJSP8rzBs6ZOnp9SRujo";
      case "startup": return "https://lh3.googleusercontent.com/aida-public/AB6AXuAEABwgp8vvFNvfMs_bR74S_Nxal4QBzcqZTvQjQ2r-uRCrAPXgHYOv19DRRuTM3kFDpM-sIsHidGi6sVHdD1Wb8jZ-nqeAzNUmjJcnNbBaLz6k1vWaBXB4WJwPG_xG-KDDB7B1azr-nSoK7lkkltbqfhdHLfuqtkZhaot2QzodDJiN7-XvgPnib70uBx7VtuGYuj6EcMMAHhEFQSBkoPb0HGtu92m8QLXJiDxxtwvmv_dzhclMD2pkyAVuLNR-5HHy5FLyRF_RHWM";
      case "education": return "https://lh3.googleusercontent.com/aida-public/AB6AXuBDMLRfL6K23YGHPKOUw5erX3KokcS4TjAcVLIrfMXuebVRhKf6lnMdEV8q3pn1IN7JMjSzMM6qNOW4sramwQ0YAjdRb31Em0-wF5Q4LdlhXJaMwuzM1dSKLRCK39ZtylaD5H2VwdSHCa6DC45giOmdQlUfwaPd2V-4EaebPUp8DshkQQvUCALwfkQjwoX6Lm4MmmWqfIexvB7BBIt98WSD9FabcdBSZUYujffpzOd8JbKolr6cq9cnNYilCpLz5yrNDWXuuSM6AUs";
      case "relationship": return "https://lh3.googleusercontent.com/aida-public/AB6AXuAtfRS5sEtFINan4jJjzV-uStnOqWkeGtAwaJD7XmZKcXIQHUldIzcyd50m0tvLDv5a9TTopJknCNAD3JkPa94lLaMnzDwYigRg8NnOUyGVIc01NAnKTFTpKrHc5a1DsD1MocC1yyIF_8c1up_RKuSTuqhM4hb3UAFTs4KcJc03B77jS97JvW9-Js3_5yKDRMuyOyaRHJGN4tsWoK146bPclobVzivltMDuO0a8jwONRdQLnb1PTFGLSM77zEUbyXNBLBGQd-ahF9Q";
      case "lifestyle": return "https://lh3.googleusercontent.com/aida-public/AB6AXuAA7zqCAJ-ojzYEqmoPjakATVxc5M68VGITKq_iNij8aDmTH5rvYQFZSBYxHJu6iJJJnRFcPcYT0G-8p6Tga_AiPfanxj_MeLsX8RNGS_2kFm1GYZENjpyKCDK0IP-KDNwP9UxApU6r4gYsVIBs0-TeiJG5Lt6AbngiXd-IKbVTGZQ9czExXU7psLcoS5se9xCv_QcLein_hhXiUxZG2O9pxJQZIMjsJmGuzLE2ubWMCqCqksCzwRYXiQ1ge9Q0b2icHN6alF2szTM";
      default: return "";
    }
  };

  return (
    <div className="bg-void min-h-screen pt-16 pb-10 overflow-x-hidden flex flex-col">
      <main className="flex-1 max-w-5xl mx-auto px-6 w-full">
        {/* Header Section */}
        <div className="mb-10">
          <p className="text-path-risk mb-2 tracking-[0.4em] text-[10px] font-display uppercase">
            Choose Your Divergence
          </p>
          <h1 className="text-2xl md:text-4xl font-display tracking-[0.1em] mb-4 leading-tight">
            Select Your <span className="text-path-risk glow-amber">Scenario</span>
          </h1>
          <p className="text-gray-400 text-sm md:text-base font-light max-w-xl leading-relaxed opacity-80">
            Every decision for something is a decision against something else. Pick a path to inhabit.
          </p>
        </div>

        {/* 3-Column Grid of Atmospheric Cards */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5 mb-16">
          {TEMPLATES.map((t) => (
            <div
              key={t.id}
              onClick={() => handleSelect(t)}
              className="group relative aspect-[4/5] overflow-hidden border border-white/10 bg-void hover:border-path-risk transition-all duration-500 cursor-pointer active:scale-95"
            >
              {/* Background with overlay */}
              <div 
                className="absolute inset-0 bg-cover bg-center transition-transform duration-700 group-hover:scale-105 opacity-25 group-hover:opacity-40"
                style={{ backgroundImage: `url('${getImageUrl(t.id)}')` }}
              />
              <div className="absolute inset-0 bg-gradient-to-t from-void via-void/30 to-transparent" />
              
              <div className="absolute inset-0 p-5 flex flex-col justify-end">
                <span className="text-path-risk text-[9px] font-display tracking-[0.3em] uppercase mb-2 opacity-50">
                   TEMPLATE
                </span>
                <h3 className="font-display text-lg font-bold mb-2 tracking-[0.1em] group-hover:text-path-risk transition-colors">{t.title}</h3>
                <p className="text-gray-400 text-[10px] font-light leading-relaxed opacity-90">
                  &ldquo;{t.question}&rdquo;
                </p>
              </div>
              
              {/* Hover highlight border */}
              <div className="absolute inset-x-0 bottom-0 h-0.5 bg-path-risk transform scale-x-0 group-hover:scale-x-100 transition-transform origin-left duration-500" />
            </div>
          ))}

          {/* Custom Path Card */}
          <div
            onClick={() => handleSelect("custom")}
            className="group relative aspect-[4/5] overflow-hidden border border-white/10 bg-void hover:border-path-safe transition-all duration-500 cursor-pointer flex flex-col items-center justify-center active:scale-95"
          >
            <div className="relative z-10 text-center p-5">
              <div className="w-10 h-10 rounded-full border border-white/10 flex items-center justify-center mb-4 group-hover:border-path-safe group-hover:bg-path-safe/10 transition-all duration-500">
                <span className="text-lg font-display text-path-safe">+</span>
              </div>
              <h3 className="font-display text-lg font-bold mb-2 tracking-[0.1em] group-hover:text-path-safe transition-colors">Custom Path</h3>
              <p className="text-gray-500 text-[10px] italic">Define your own divergence.</p>
            </div>
            
             {/* Hover highlight border */}
             <div className="absolute inset-x-0 bottom-0 h-0.5 bg-path-safe transform scale-x-0 group-hover:scale-x-100 transition-transform origin-left duration-500" />
          </div>
        </div>
      </main>

      {/* Aligned Footer */}
      <footer className="py-8 border-t border-white/10 text-center mt-auto">
        <div className="max-w-7xl mx-auto px-6 flex flex-col md:flex-row justify-between items-center gap-4">
          <p className="text-gray-600 text-[10px] tracking-widest">&copy; 2025 DIVERGE &mdash; TEAM SIC MUNDUS</p>
          <p className="text-gray-600 text-[9px] italic opacity-60">Sic Mundus Creatus Est &mdash; Thus the world is created.</p>
        </div>
      </footer>
    </div>
  );
}
