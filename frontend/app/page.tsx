import { Navbar } from "@/components/landing/Navbar";
import { HeroSection } from "@/components/landing/HeroSection";
import { SocialProofSection } from "@/components/landing/SocialProofSection";
import { ProblemSection } from "@/components/landing/ProblemSection";
import { HowItWorksSection } from "@/components/landing/HowItWorksSection";
import { FeaturesSection } from "@/components/landing/FeaturesSection";
import { ComparisonSection } from "@/components/landing/ComparisonSection";
import { BmoniSection } from "@/components/landing/BmoniSection";
import { TestimonialsSection } from "@/components/landing/TestimonialsSection";
import { FAQSection } from "@/components/landing/FAQSection";
import { PricingSection } from "@/components/landing/PricingSection";
import { NewsletterSection } from "@/components/landing/NewsletterSection";
import { FooterCTA } from "@/components/landing/FooterCTA";

export default function Home() {
  return (
    <main className="transition-colors duration-500">
      <Navbar />
      <HeroSection />
      <SocialProofSection />
      <ProblemSection />
      <HowItWorksSection />
      <FeaturesSection />
      <ComparisonSection />
      <BmoniSection />
      <TestimonialsSection />
      <FAQSection />
      <PricingSection />
      <NewsletterSection />
      <FooterCTA />
    </main>
  );
}
