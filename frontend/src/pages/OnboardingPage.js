import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import axios from "axios";
import { toast } from "sonner";
import { useAuth } from "../App";
import { ChevronRight, ChevronLeft, Check } from "lucide-react";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const INTEREST_CATEGORIES = {
  Politics: { emoji: "🏛️", subcategories: ["Parliament", "Elections", "Judiciary", "International Relations", "State Politics"] },
  Technology: { emoji: "💻", subcategories: ["AI & ML", "Startups", "Gadgets", "Fintech", "Space Tech", "Telecom"] },
  Business: { emoji: "📈", subcategories: ["Markets", "Economy", "Startups", "Real Estate", "Banking", "Corporate"] },
  Sports: { emoji: "🏏", subcategories: ["Cricket", "Football", "Tennis", "Olympics", "Kabaddi", "Motorsport"] },
  Entertainment: { emoji: "🎬", subcategories: ["Bollywood", "OTT", "Music", "Television", "Regional Cinema"] },
  Science: { emoji: "🔬", subcategories: ["Space", "Health", "Environment", "Research", "Climate"] },
  World: { emoji: "🌍", subcategories: ["USA", "China", "Europe", "Middle East", "Southeast Asia"] },
  Lifestyle: { emoji: "✨", subcategories: ["Travel", "Food", "Fashion", "Wellness", "Automobiles"] }
};

const OnboardingPage = () => {
  const navigate = useNavigate();
  const { checkAuth } = useAuth();
  const [step, setStep] = useState(1);
  const [selectedCategories, setSelectedCategories] = useState([]);
  const [selectedSubcategories, setSelectedSubcategories] = useState({});
  const [activeCategory, setActiveCategory] = useState(null);
  const [loading, setLoading] = useState(false);

  const toggleCategory = (category) => {
    if (selectedCategories.includes(category)) {
      setSelectedCategories(selectedCategories.filter(c => c !== category));
      const newSubs = { ...selectedSubcategories };
      delete newSubs[category];
      setSelectedSubcategories(newSubs);
    } else {
      setSelectedCategories([...selectedCategories, category]);
      setActiveCategory(category);
    }
  };

  const toggleSubcategory = (category, sub) => {
    const current = selectedSubcategories[category] || [];
    if (current.includes(sub)) {
      setSelectedSubcategories({
        ...selectedSubcategories,
        [category]: current.filter(s => s !== sub)
      });
    } else {
      setSelectedSubcategories({
        ...selectedSubcategories,
        [category]: [...current, sub]
      });
    }
  };

  const handleComplete = async () => {
    if (selectedCategories.length < 3) {
      toast.error("Please select at least 3 categories");
      return;
    }

    setLoading(true);
    try {
      await axios.put(
        `${API}/users/interests`,
        { interests: selectedCategories },
        { withCredentials: true }
      );
      await checkAuth();
      toast.success("Your news feed is ready!");
      navigate("/feed", { replace: true });
    } catch (error) {
      console.error("Error saving interests:", error);
      toast.error("Failed to save preferences");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#0A0A0A] relative overflow-hidden">
      {/* Background glow */}
      <div className="absolute inset-0 surya-glow opacity-20" />

      {/* Progress bar */}
      <div className="fixed top-0 left-0 right-0 h-1 bg-[#171717] z-50">
        <motion.div 
          className="h-full bg-red-600"
          initial={{ width: "0%" }}
          animate={{ width: `${(step / 3) * 100}%` }}
          transition={{ duration: 0.3 }}
        />
      </div>

      <div className="relative z-10 max-w-2xl mx-auto px-6 py-12">
        <AnimatePresence mode="wait">
          {/* Step 1: Welcome */}
          {step === 1 && (
            <motion.div
              key="step1"
              initial={{ opacity: 0, x: 50 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -50 }}
              className="text-center pt-20"
            >
              <h1 className="font-serif text-4xl md:text-5xl font-bold text-white mb-6">
                Welcome to Chintan
              </h1>
              <p className="text-gray-400 text-lg mb-4">
                News that makes you think, not just scroll.
              </p>
              <p className="text-gray-500 mb-12">
                Let's personalize your experience in 3 quick steps.
              </p>

              <div className="space-y-6 text-left max-w-sm mx-auto mb-12">
                <div className="flex items-start gap-4">
                  <div className="w-8 h-8 rounded-full bg-red-600/20 flex items-center justify-center text-red-500 font-mono text-sm">1</div>
                  <div>
                    <p className="text-white font-medium">Choose your interests</p>
                    <p className="text-gray-500 text-sm">Select topics you care about</p>
                  </div>
                </div>
                <div className="flex items-start gap-4">
                  <div className="w-8 h-8 rounded-full bg-red-600/20 flex items-center justify-center text-red-500 font-mono text-sm">2</div>
                  <div>
                    <p className="text-white font-medium">Pick subcategories</p>
                    <p className="text-gray-500 text-sm">Fine-tune your preferences</p>
                  </div>
                </div>
                <div className="flex items-start gap-4">
                  <div className="w-8 h-8 rounded-full bg-red-600/20 flex items-center justify-center text-red-500 font-mono text-sm">3</div>
                  <div>
                    <p className="text-white font-medium">Start contemplating</p>
                    <p className="text-gray-500 text-sm">Your personalized feed awaits</p>
                  </div>
                </div>
              </div>

              <button
                onClick={() => setStep(2)}
                className="btn-primary flex items-center gap-2 mx-auto"
                data-testid="onboarding-start-btn"
              >
                Let's Begin <ChevronRight className="w-5 h-5" />
              </button>
            </motion.div>
          )}

          {/* Step 2: Select Categories */}
          {step === 2 && (
            <motion.div
              key="step2"
              initial={{ opacity: 0, x: 50 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -50 }}
              className="pt-12"
            >
              <h2 className="font-serif text-3xl font-bold text-white mb-2 text-center">
                What interests you?
              </h2>
              <p className="text-gray-500 text-center mb-8">
                Select at least 3 categories ({selectedCategories.length} selected)
              </p>

              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
                {Object.entries(INTEREST_CATEGORIES).map(([category, { emoji }]) => (
                  <motion.button
                    key={category}
                    onClick={() => toggleCategory(category)}
                    className={`relative p-4 rounded-xl border transition-colors ${
                      selectedCategories.includes(category)
                        ? "bg-red-600/20 border-red-600"
                        : "bg-[#171717] border-white/10 hover:border-white/20"
                    }`}
                    whileHover={{ scale: 1.02 }}
                    whileTap={{ scale: 0.98 }}
                    data-testid={`category-${category.toLowerCase()}`}
                  >
                    {selectedCategories.includes(category) && (
                      <motion.div
                        initial={{ scale: 0 }}
                        animate={{ scale: 1 }}
                        className="absolute top-2 right-2 w-5 h-5 bg-red-600 rounded-full flex items-center justify-center"
                      >
                        <Check className="w-3 h-3 text-white" />
                      </motion.div>
                    )}
                    <span className="text-3xl mb-2 block">{emoji}</span>
                    <span className="text-white text-sm font-medium">{category}</span>
                  </motion.button>
                ))}
              </div>

              {/* Subcategory Modal */}
              <AnimatePresence>
                {activeCategory && selectedCategories.includes(activeCategory) && (
                  <motion.div
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: 20 }}
                    className="glass-card rounded-xl p-6 mb-8"
                  >
                    <div className="flex items-center justify-between mb-4">
                      <h3 className="text-white font-medium">
                        {INTEREST_CATEGORIES[activeCategory].emoji} {activeCategory} Subcategories
                      </h3>
                      <button 
                        onClick={() => setActiveCategory(null)}
                        className="text-gray-500 hover:text-white text-sm"
                      >
                        Done
                      </button>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      {INTEREST_CATEGORIES[activeCategory].subcategories.map(sub => (
                        <button
                          key={sub}
                          onClick={() => toggleSubcategory(activeCategory, sub)}
                          className={`px-3 py-1.5 rounded-full text-sm transition-colors ${
                            (selectedSubcategories[activeCategory] || []).includes(sub)
                              ? "bg-red-600 text-white"
                              : "bg-white/5 text-gray-400 hover:bg-white/10"
                          }`}
                          data-testid={`subcategory-${sub.toLowerCase().replace(/\s+/g, '-')}`}
                        >
                          {sub}
                        </button>
                      ))}
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>

              <div className="flex justify-between">
                <button
                  onClick={() => setStep(1)}
                  className="btn-secondary flex items-center gap-2"
                >
                  <ChevronLeft className="w-5 h-5" /> Back
                </button>
                <button
                  onClick={() => setStep(3)}
                  disabled={selectedCategories.length < 3}
                  className={`btn-primary flex items-center gap-2 ${
                    selectedCategories.length < 3 ? "opacity-50 cursor-not-allowed" : ""
                  }`}
                  data-testid="onboarding-next-btn"
                >
                  Continue <ChevronRight className="w-5 h-5" />
                </button>
              </div>
            </motion.div>
          )}

          {/* Step 3: Confirmation */}
          {step === 3 && (
            <motion.div
              key="step3"
              initial={{ opacity: 0, x: 50 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -50 }}
              className="pt-12 text-center"
            >
              <motion.div
                initial={{ scale: 0 }}
                animate={{ scale: 1 }}
                transition={{ type: "spring", delay: 0.2 }}
                className="w-20 h-20 bg-red-600/20 rounded-full flex items-center justify-center mx-auto mb-6"
              >
                <Check className="w-10 h-10 text-red-500" />
              </motion.div>

              <h2 className="font-serif text-3xl font-bold text-white mb-4">
                You're all set!
              </h2>
              <p className="text-gray-400 mb-8">
                Your personalized news feed is ready
              </p>

              <div className="glass-card rounded-xl p-6 text-left mb-8 max-w-md mx-auto">
                <p className="text-gray-500 text-sm mb-3">Your interests:</p>
                <div className="flex flex-wrap gap-2">
                  {selectedCategories.map(cat => (
                    <span key={cat} className="px-3 py-1 bg-red-600/20 text-red-400 rounded-full text-sm">
                      {INTEREST_CATEGORIES[cat].emoji} {cat}
                    </span>
                  ))}
                </div>
              </div>

              <div className="flex justify-between max-w-md mx-auto">
                <button
                  onClick={() => setStep(2)}
                  className="btn-secondary flex items-center gap-2"
                >
                  <ChevronLeft className="w-5 h-5" /> Back
                </button>
                <button
                  onClick={handleComplete}
                  disabled={loading}
                  className="btn-primary flex items-center gap-2"
                  data-testid="onboarding-complete-btn"
                >
                  {loading ? "Setting up..." : "Start Reading"} <ChevronRight className="w-5 h-5" />
                </button>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
};

export default OnboardingPage;
