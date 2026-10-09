"""The vocabulary for the word cloud on the Software and About pages.

build_wordcloud.py counts these terms in the text of index.html and the CV, and
the cloud is drawn from the counts. Edit this file to change what appears.

* LEX: one line per word in the cloud: (label shown, kind, regular expression).
  - kind is "topic", "method" (both drawn blue) or "tool" (orange, bold).
  - Lines are applied top to bottom and every match is removed from the text, so a
    phrase is never counted twice. Put longer phrases above the shorter words
    inside them (for example "DNA barcode gap" above "DNA barcoding").
  - Matching ignores case unless the label is listed in CASE_SENSITIVE.
* STRIP: phrases removed before counting, such as journal and venue names, which
  contain topic words but are not topics.
* HIDE: terms that are counted but never shown because they are too general.
* MIN_COUNT: a term needs at least this many mentions to appear, except the
  terms in ALWAYS_SHOW.
"""

MIN_COUNT = 2
ALWAYS_SHOW = {"Stan"}
HIDE = {"estimation", "data", "detection", "computational", "population dynamics", "occupancy modelling"}
CASE_SENSITIVE = {"R", "Stan", "VLF", "GBADs", "CRAN", "Shiny", "Python", "HACSim", "RulesTools", "eDNA"}

# ---- 1. remove text that names venues, journals and book series (they contain topic words but are not topics) ----
STRIP = [
 r"International Barcode of Life Conference", r"\bIBOL\d?\b", r"\biBOL\b", r"Barcode Bulletin", r"DNA Barcoding Blog",
 r"DNA Barcodes,", r"DNA Barcoding\. Methods in Molecular Biology",
 r"Frontiers in Ecology and Evolution", r"Methods in Ecology and Evolution", r"Ecology and Evolution",
 r"Molecular Ecology Resources", r"Biodiversity Data Journal", r"Journal of Food Science", r"PeerJ Computer Science",
 r"Canadian (?:Artificial Intelligence )?Conference on Artificial Intelligence", r"Canadian Artificial Intelligence Conference",
 r"Artificial Intelligence and Machine Learning in Biology", r"Pathway to Increase Standards and Competency[^.\n]*?Surveys",
 r"Applied Mathematics, Modelling, and Computational Science",
 r"Computational Sciences", r"Mathematical, and Physical Sciences",
 r"Advancing Research Impact Fund", r"Food [Ff]rom Thought",
 r"Global Burden of Animal Diseases",
 r"Curriculum Vitae", r"Course Instructor",
 r"CIS\*\d+[^\n]*", r"STAT\*\d+[^\n]*", r"IBIO\*\d+[^\n]*", r"BINF\*\d+", r"MCB\*\d+/?\d*",
 r"Discrete Stuctures in Computing", r"System Modelling and Simulation", r"Modelling of Computer Systems",
]
# ---- 2. lexicon, applied in order; each match is consumed so nothing is counted twice ----
# (label, category, regex)   category: topic | method | tool
LEX = [
 ("DNA barcode gap","topic", r"(?:DNA )?barcode gap"),
 ("eDNA","topic",           r"environmental DNA(?: \(eDNA\))?|\(e\)DNA|\beDNA\b"),
 ("DNA barcoding","topic",  r"DNA barcod\w*|\bbarcod\w*"),
 ("biodiversity","topic",   r"biodiversity"),
 ("species identification","topic", r"(?:molecular )?species identification|specimen identification|taxon identification|species delimitation|delimiting species|species discovery"),
 ("genetic diversity","topic", r"genetic diversity|haplotype (?:sampling )?diversity|genetic variation"),
 ("haplotype accumulation","topic", r"haplotype accumulation(?: curves?)?"),
 ("sampling","topic",       r"\bsampl\w+|sample sizes?"),
 ("seafood fraud","topic",  r"seafood(?: product)?[ -](?:fraud|mislabel\w*)|\bfraud\w*|\bmislabel\w*|\bseafood\b"),
 ("supply chain","topic",   r"supply chain"),
 ("disease burden","topic", r"disease burden"),
 ("livestock","topic",      r"livestock"),
 ("GBADs","topic",          r"\bGBADs?\b"),
 ("butterflies","topic",    r"butterfl\w+"),
 ("fishes","topic",         r"ray-finned fishes|\bfish(?:es)?\b"),
 ("evolutionary biology","topic", r"evolutionary biology|evolutionary"),
 ("ecology","topic",        r"\becolog\w*"),
 ("genomics","topic",       r"genomics"),
 ("bioinformatics","topic", r"bioinformatics|biodiversity informatics"),
 ("conservation","topic",   r"conservation"),
 ("metadata","topic",       r"metadata"),
 ("DNA sequences","topic",   r"DNA sequences?|sequence data|\bsequences?\b"),
 ("species","topic",       r"\bspecies\b"),
 ("intraspecific","topic",  r"intraspecific"),
 ("detection","topic",     r"\bdetection\b"),
 ("population dynamics","topic", r"\bpopulation\b"),
 ("sequencing errors","topic", r"very low frequency variants?|sequencing and PCR errors?"),
 ("computational","method", r"\bcomputational\b"),
 ("estimation","method",   r"\bestimat\w+"),
 ("Bayesian","method",      r"\bBayesian\b"),
 ("machine learning","method", r"machine learning|\bML\b"),
 ("artificial intelligence","method", r"artificial intelligence|\bAI\b"),
 ("association rules","method", r"association rules?(?: mining)?|rule mining|\brules?\b"),
 ("statistical modelling","method", r"statistical model\w*"),
 ("statistics","method",    r"\bstatistic\w*"),
 ("modelling","method",     r"\bmodel(?:l?ing|led)?s?\b"),
 ("data science","method",  r"data science"),
 ("data mining","method",   r"data mining|\bmining\b"),
 ("bootstrap","method",     r"bootstrap\w*"),
 ("kernel density estimation","method", r"kernel density(?: estimat\w+)?|kernel methods"),
 ("regression","method",    r"regression"),
 ("time series","method",   r"time[- ]series"),
 ("spatiotemporal","method", r"spatiotemporal"),
 ("optimization","method",  r"optimi[sz]ation"),
 ("simulation","method",    r"simulat\w+|Monte Carlo"),
 ("coalescent","method",    r"coalescent"),
 ("nonparametric","method", r"nonparametric|semiparametric"),
 ("classification","method", r"classification|clustering"),
 ("generalized additive models","method", r"generalized additive models?|\bGAMs?\b"),
 ("Gaussian processes","method", r"Gaussian processes?|Kriging"),
 ("genetic algorithms","method", r"genetic algorithms?|simulated annealing|random search"),
 ("occupancy modelling","method", r"occupancy"),
 ("data","method",         r"\bdata(?:sets?)?\b"),
 ("agent-based models","method", r"agent-based|individual-based|equation-based|dynamical system|dynamical modelling"),
 ("HACSim","tool",         r"\bHACSim\b"),
 ("VLF","tool",            r"\bVLF\b"),
 ("RulesTools","tool",     r"\bRulesTools\b"),
 ("Shiny","tool",          r"\bShiny\b"),
 ("CRAN","tool",           r"\bCRAN\b"),
 ("Python","tool",         r"\bPython\b"),
 ("Stan","tool",           r"\bStan\b"),
 ("R","tool",              r"\bR(?= (?:package|packages|Shiny|scripts|reporting|versions|software|and Stan|web))|(?<=\bin )R\b(?![.\w])|(?<=employ )R\b|(?<=using )R\b"),
 ("web apps","tool",       r"web app\w*"),
]

