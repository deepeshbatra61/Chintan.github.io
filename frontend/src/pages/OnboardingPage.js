import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import axios from "axios";
import { toast } from "sonner";
import { useAuth } from "../App";
import { ChevronRight, ChevronLeft, Check, ChevronDown } from "lucide-react";

const BACKEND_URL = "https://chintangithubio-production.up.railway.app";
const API = `${BACKEND_URL}/api`;

const INTEREST_CATEGORIES = {
  Politics: { 
    description: "Government, elections, policy", 
    subcategories: ["Parliament", "Elections", "Judiciary", "International Relations", "State Politics"] 
  },
  Technology: { 
    description: "Innovation, startups, digital", 
    subcategories: ["AI & ML", "Startups", "Gadgets", "Fintech", "Space Tech", "Telecom"] 
  },
  Business: { 
    description: "Markets, economy, corporate", 
    subcategories: ["Markets", "Economy", "Startups", "Real Estate", "Banking", "Corporate"] 
  },
  Sports: { 
    description: "Cricket, football, athletics", 
    subcategories: ["Cricket", "Football", "Tennis", "Olympics", "Kabaddi", "Motorsport"] 
  },
  Entertainment: { 
    description: "Cinema, music, culture", 
    subcategories: ["Bollywood", "OTT", "Music", "Television", "Regional Cinema"] 
  },
  Science: { 
    description: "Research, health, climate", 
    subcategories: ["Space", "Health", "Environment", "Research", "Climate"] 
  },
  World: { 
    description: "Global affairs, geopolitics", 
    subcategories: ["USA", "China", "Europe", "Middle East", "Southeast Asia"] 
  },
  Lifestyle: { 
    description: "Travel, food, wellness", 
    subcategories: ["Travel", "Food", "Fashion", "Wellness", "Automobiles"] 
  }
};

const OnboardingPage = () => {
  const navigate = useNavigate();
  const { checkAuth } = useAuth();
  const [step, setStep] = useState(1);
  const [selectedCategories, setSelectedCategories] = useState([]);
  const [selectedSubcategories, setSelectedSubcategories] = useState({});
  const [expandedCategory, setExpandedCategory] = useState(null);
  const [loading, setLoading] = useState(false);

  const toggleCategory = (category) => {
    if (selectedCategories.includes(category)) {
      setSelectedCategories(selectedCategories.filter(c => c !== category));
      const newSubs = { ...selectedSubcategories };
      delete newSubs[category];
      setSelectedSubcategories(newSubs);
      if (expandedCategory === category) setExpandedCategory(null);
    } else {
      setSelectedCategories([...selectedCategories, category]);
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
      toast.error("Please select at least 3 topics");
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
      {/* Subtle background glow */}
      <div className="fixed inset-0 pointer-events-none">
        <div className="absolute top-1/4 left-1/2 -translate-x-1/2 w-[400px] h-[400px] bg-red-500/5 rounded-full blur-3xl" />
      </div>

      {/* Progress bar */}
      <div className="fixed top-0 left-0 right-0 h-0.5 bg-[#1a1a1a] z-50">
        <motion.div 
          className="h-full bg-red-600"
          initial={{ width: "0%" }}
          animate={{ width: `${(step / 2) * 100}%` }}
          transition={{ duration: 0.3 }}
        />
      </div>

      <div className="relative z-10 max-w-2xl mx-auto px-6 py-16">
        <AnimatePresence mode="wait">
          {/* Step 1: Welcome */}
          {step === 1 && (
            <motion.div
              key="step1"
              initial={{ opacity: 0, x: 50 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -50 }}
              className="pt-8"
            >
              <div className="text-center mb-12">
                <h1 className="font-serif text-4xl md:text-5xl font-bold text-white mb-4">
                  Welcome to Chintan
                </h1>
                <p className="text-gray-400 text-lg">
                  Let's personalize your news experience
                </p>
              </div>

              <div className="mb-8">
                <p className="text-gray-500 text-sm mb-6 text-center">
                  Select at least 3 topics you're interested in
                </p>

                {/* Category Grid - Professional Design */}
                <div className="space-y-3">
                  {Object.entries(INTEREST_CATEGORIES).map(([category, { description, subcategories }]) => (
                    <div key={category}>
                      <button
                        onClick={() => toggleCategory(category)}
                        className={`w-full p-4 rounded-xl border transition-all ${
                          selectedCategories.includes(category)
                            ? "bg-red-950/40 border-red-600/50"
                            : "bg-white/[0.02] border-white/10 hover:border-white/20"
                        }`}
                        data-testid={`category-${category.toLowerCase()}`}
                      >
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-4">
                            {/* Checkbox style indicator */}
                            <div className={`w-5 h-5 rounded border-2 flex items-center justify-center transition-colors ${
                              selectedCategories.includes(category)
                                ? "bg-red-600 border-red-600"
                                : "border-gray-600"
                            }`}>
                              {selectedCategories.includes(category) && (
                                <Check className="w-3 h-3 text-white" />
                              )}
                            </div>
                            <div className="text-left">
                              <p className="text-white font-medium">{category}</p>
                              <p className="text-gray-500 text-sm">{description}</p>
                            </div>
                          </div>
                          
                          {selectedCategories.includes(category) && (
                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                setExpandedCategory(expandedCategory === category ? null : category);
                              }}
                              className="p-1 hover:bg-white/10 rounded transition-colors"
                            >
                              <ChevronDown className={`w-4 h-4 text-gray-500 transition-transform ${
                                expandedCategory === category ? "rotate-180" : ""
                              }`} />
                            </button>
                          )}
                        </div>
                      </button>

                      {/* Subcategories - Optional */}
                      <AnimatePresence>
                        {expandedCategory === category && selectedCategories.includes(category) && (
                          <motion.div
                            initial={{ height: 0, opacity: 0 }}
                            animate={{ height: "auto", opacity: 1 }}
                            exit={{ height: 0, opacity: 0 }}
                            className="overflow-hidden"
                          >
                            <div className="pt-2 pb-1 px-4">
                              <p className="text-gray-600 text-xs mb-2">
                                Fine-tune your interests (optional)
                              </p>
                              <div className="flex flex-wrap gap-2">
                                {subcategories.map(sub => (
                                  <button
                                    key={sub}
                                    onClick={() => toggleSubcategory(category, sub)}
                                    className={`px-3 py-1.5 rounded-lg text-xs transition-colors ${
                                      (selectedSubcategories[category] || []).includes(sub)
                                        ? "bg-red-600/30 text-red-400 border border-red-600/50"
                                        : "bg-white/5 text-gray-400 hover:bg-white/10 border border-transparent"
                                    }`}
                                    data-testid={`subcategory-${sub.toLowerCase().replace(/\s+/g, '-')}`}
                                  >
                                    {sub}
                                  </button>
                                ))}
                              </div>
                            </div>
                          </motion.div>
                        )}
                      </AnimatePresence>
                    </div>
                  ))}
                </div>
              </div>

              {/* Selection count */}
              <div className="text-center mb-6">
                <p className={`text-sm ${selectedCategories.length >= 3 ? 'text-green-500' : 'text-gray-500'}`}>
                  {selectedCategories.length} of 3 minimum selected
                </p>
              </div>

              <button
                onClick={() => setStep(2)}
                disabled={selectedCategories.length < 3}
                className={`w-full py-4 rounded-xl font-medium transition-all flex items-center justify-center gap-2 ${
                  selectedCategories.length >= 3
                    ? "bg-red-600 text-white hover:bg-red-700"
                    : "bg-white/5 text-gray-600 cursor-not-allowed"
                }`}
                data-testid="onboarding-next-btn"
              >
                Continue <ChevronRight className="w-5 h-5" />
              </button>
            </motion.div>
          )}

          {/* Step 2: Confirmation */}
          {step === 2 && (
            <motion.div
              key="step2"
              initial={{ opacity: 0, x: 50 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -50 }}
              className="pt-12 text-center"
            >
              <motion.div
                initial={{ scale: 0 }}
                animate={{ scale: 1 }}
                transition={{ type: "spring", delay: 0.2 }}
                className="w-20 h-20 bg-red-600/20 rounded-full flex items-center justify-center mx-auto mb-8"
              >
                <Check className="w-10 h-10 text-red-500" />
              </motion.div>

              <h2 className="font-serif text-3xl font-bold text-white mb-4">
                You're all set
              </h2>
              <p className="text-gray-400 mb-8">
                Your personalized news feed is ready
              </p>

              <div className="glass-card rounded-xl p-6 text-left mb-8 max-w-md mx-auto">
                <p className="text-gray-500 text-sm mb-3">Your interests</p>
                <div className="flex flex-wrap gap-2">
                  {selectedCategories.map(cat => (
                    <span 
                      key={cat} 
                      className="px-3 py-1.5 bg-red-600/20 text-red-400 rounded-lg text-sm font-medium"
                    >
                      {cat}
                    </span>
                  ))}
                </div>
              </div>

              <div className="flex gap-4 max-w-md mx-auto">
                <button
                  onClick={() => setStep(1)}
                  className="flex-1 py-3 rounded-xl bg-white/5 text-gray-400 hover:bg-white/10 transition-colors flex items-center justify-center gap-2"
                >
                  <ChevronLeft className="w-5 h-5" /> Back
                </button>
                <button
                  onClick={handleComplete}
                  disabled={loading}
                  className="flex-1 py-3 rounded-xl bg-red-600 text-white hover:bg-red-700 transition-colors flex items-center justify-center gap-2"
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
