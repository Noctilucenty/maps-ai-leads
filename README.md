# AI Business Lead Engine

![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
![Status](https://img.shields.io/badge/status-active-success)
![License](https://img.shields.io/badge/license-MIT-green)
![Google Places API](https://img.shields.io/badge/API-Google%20Places-orange)

A Python pipeline that collects local business leads from **Google Maps**, enriches their websites, and ranks them for outreach using simple opportunity scoring.

Built for finding businesses that may benefit from:

- AI receptionists
- missed-call SMS recovery
- appointment booking automation
- lead capture systems

---

# Overview

This project turns raw Google Maps business listings into a more useful outreach-ready dataset.

### Pipeline

Google Maps API  
↓  
Lead Collector  
↓  
Website Enrichment  
↓  
Lead Scoring  
↓  
Outreach-Ready CSV  

---

# Features

## Google Maps Lead Collection

Extracts business data using the Google Places API:

- business name  
- address  
- phone number  
- website  
- rating  
- review count  
- Google Maps URL  

---

## Website Enrichment

Scans business websites to detect:

- emails  
- Instagram / Facebook / LinkedIn  
- contact forms  
- booking pages  
- tech stack clues  
- contact / about / booking URLs  

---

## Lead Scoring

Ranks each business based on signals such as:

- website presence  
- contact options  
- reviews and rating  
- booking availability  
- outreach opportunity  

---

# Example Output

| Business | Rating | Reviews | Booking | Lead Score | Pitch Angle |
|----------|--------|---------|---------|------------|-------------|
| AutoTech Repair | 4.6 | 120 | No | 78 | AI booking + missed-call auto text |
| City Dental | 4.7 | 230 | Yes | 55 | Overflow call handling |
| Quick HVAC | 4.2 | 45 | No | 70 | AI receptionist + SMS lead capture |

---

# Installation

Clone the repository:

git clone https://github.com/Noctilucenty/maps-ai-leads.git  
cd maps-ai-leads  

Install dependencies:

pip install -r requirements.txt  

---

# Environment Setup

Create a `.env` file:

GOOGLE_MAPS_API_KEY=your_api_key_here  

Get your API key from Google Cloud Console and enable the **Places API**.

---

# Usage

## Step 1 — Collect Businesses

Example: auto repair shops in San Jose

python google_maps_lead_collector.py --mode text --query "auto repair shops in San Jose CA" --output leads.csv

This creates:

leads.csv

---

## Step 2 — Enrich Websites

python site_enricher.py --input leads.csv --output enriched_leads.csv

This adds:

- emails  
- social links  
- booking detection  
- tech stack  
- lead score  
- pitch suggestions  

---

# Example Workflow

python google_maps_lead_collector.py --mode text --query "auto repair shops in San Jose CA" --output leads.csv  

python site_enricher.py --input leads.csv --output enriched_leads.csv  

---

# Project Structure

maps-ai-leads/

google_maps_lead_collector.py  
site_enricher.py  
requirements.txt  
README.md  
.gitignore  
LICENSE  
assets/

---

# Requirements

Python 3.10+

Libraries:

requests  
pandas  
beautifulsoup4  
lxml  

---

# Use Cases

This tool can help with:

- lead generation  
- local business research  
- automation consulting  
- outbound sales prospecting  
- market intelligence  

---

# Future Improvements

Potential upgrades:

- multi-city scraping  
- email verification  
- AI outreach message generation  
- CRM integrations  
- web dashboard  
- niche-specific lead scoring  

---

# Disclaimer

This project uses the official **Google Places API**.  
Make sure your usage complies with Google's API terms.

Do not commit:

.env  
API keys  
private lead files  

---

# Author

Leon Kelvin Li  

GitHub:  
https://github.com/Noctilucenty  

---

# License

MIT License
