import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import './Home.css';
import logoForm from './assets/logoForm 1.svg';
import heroIllustration from './assets/4146248_2205941 1.png';
import ellipseBackground from './assets/Ellipse 22.png';
import frameImage from './assets/Frame 285.png';

export default function Home() {
  const [prompt, setPrompt] = useState('');
  const navigate = useNavigate();

  const handleGenerate = () => {
    console.log('Generate button clicked');
    console.log('Prompt value:', prompt);
    
    if (prompt.trim()) {
      console.log('Navigating to form-builder with prompt:', prompt.trim());
      navigate(`/form-builder?prompt=${encodeURIComponent(prompt.trim())}`);
    } else {
      console.log('No prompt entered');
      alert('Please enter a prompt first');
    }
  };
  return (
    <div className="home-container">
      {/* Navigation Bar */}
      <nav className="home-navbar">
        <div className="navbar-left">
          <div className="navbar-logo">
            <img src={logoForm} alt="FORMAVERSE" className="logo-icon" />
          </div>
        </div>
        
        <div className="navbar-center">
          <div className="nav-links">
            <button className="nav-link active">Home</button>
            <button className="nav-link">About</button>
            <button className="nav-link">Template</button>
            <button className="nav-link">Themes</button>
          </div>
        </div>
        
        <div className="navbar-right">
          <div className="bot-icon">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
              <rect x="4" y="6" width="16" height="12" rx="2" fill="#4F46E5"/>
              <circle cx="8" cy="10" r="1" fill="white"/>
              <circle cx="16" cy="10" r="1" fill="white"/>
              <path d="M8 14h8" stroke="white" strokeWidth="1.5" strokeLinecap="round"/>
            </svg>
          </div>
        </div>
      </nav>

      {/* Hero Section */}
      <div className="hero-container">
        <div className="hero-content">
          <div className="hero-left">
            <h1 className="hero-title">
              <span className="title-line-1">Online Form</span>
              <span className="title-line-2">Builder</span>
            </h1>
            <p className="hero-subtitle">That Completes Your Workflows</p>
            <p className="hero-description">
              Harness the power of AI to create intelligent forms that adapt to your workflow.
              Just enter a prompt, choose your structure, and let Formaverse shape your
              universe of data.
            </p>
            
            <div className="hero-input-section">
              <div className="input-container">
                <input 
                  type="text" 
                  placeholder=""
                  className="hero-input"
                  value={prompt}
                  onChange={(e) => setPrompt(e.target.value)}
                />
                <button 
                  className="generate-btn"
                  onClick={handleGenerate}
                >
                  Generate
                  <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                    <path d="M8 3l5 5-5 5M13 8H3" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                  </svg>
                </button>
              </div>
            </div>
            
            <div className="trust-indicators">
              <div className="trust-item">
                <span className="trust-badge">Trusted by 100k+</span>
                <span className="trust-text">users worldwide</span>
              </div>
              
              <div className="features-list">
                <div className="feature-item">
                  <span className="check-icon">✓</span>
                  <span>Unlimited Forms</span>
                </div>
                <div className="feature-item">
                  <span className="check-icon">✓</span>
                  <span>Unlimited Responses</span>
                </div>
                <div className="feature-item">
                  <span className="check-icon">✓</span>
                  <span>No Credit Card Required</span>
                </div>
              </div>
            </div>
          </div>
          
          <div className="hero-right">
            <div className="hero-illustration">
              <img src={ellipseBackground} alt="Background" className="background-ellipse" />
              
              {/* Floating document elements behind the character */}
              <div className="floating-docs">
                <div className="doc-element doc-1">
                  <div className="doc-header"></div>
                  <div className="doc-lines">
                    <div className="doc-line"></div>
                    <div className="doc-line"></div>
                    <div className="doc-line"></div>
                  </div>
                </div>
                
                <div className="doc-element doc-2">
                  <div className="doc-header"></div>
                  <div className="doc-lines">
                    <div className="doc-line"></div>
                    <div className="doc-line"></div>
                    <div className="doc-line short"></div>
                  </div>
                </div>
                
                <div className="doc-element doc-3">
                  <div className="doc-header"></div>
                  <div className="doc-lines">
                    <div className="doc-line"></div>
                    <div className="doc-line"></div>
                    <div className="doc-line"></div>
                    <div className="doc-line short"></div>
                  </div>
                </div>
                
                <div className="doc-element doc-4">
                  <div className="doc-header small"></div>
                  <div className="doc-lines">
                    <div className="doc-line"></div>
                    <div className="doc-line short"></div>
                  </div>
                </div>
              </div>
              
              <img src={heroIllustration} alt="Form Builder Illustration" className="illustration-img" />
              {/* <img src={frameImage} alt="Frame" className="frame-decoration" /> */}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}