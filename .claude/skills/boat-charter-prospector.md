---
name: boat-charter-prospector
description: >
  Scrape and compile comprehensive lists of boat rental operators, fishing charters, sailboat operators,
  and individual boat rental operators for Boatsetter/Getmyboat prospecting. Use this skill whenever
  the user mentions prospecting for boat charters, finding boat rental operators, building lead lists
  for Boatsetter or Getmyboat, scraping charter companies, DMA-based boat operator searches, or
  anything related to discovering and cataloguing boat/charter/rental businesses in a geographic area.
  Also trigger when the user mentions "DMA", "designated market area", "boat leads", "charter leads",
  "boat rental spreadsheet", "fishing charter list", or wants to find operators who are NOT yet on
  Boatsetter/Getmyboat. This skill produces a formatted .xlsx spreadsheet with all discovered operators.
---

# Boat Charter Prospector

Build comprehensive lead lists of boat rental operators, fishing charters, sailboat operators, and
individual boat rental owners within a specified DMA (Designated Market Area) for Boatsetter/Getmyboat
sales prospecting.

## Overview

This skill systematically searches for every boat charter and rental operator within a user-specified
DMA region, then outputs a professionally formatted .xlsx spreadsheet ready for sales outreach.

## Required Columns (in order)

| Column | Description |
|--------|-------------|
| Charter Name | Business name of the charter/rental company |
| Owner Name | Owner or primary contact name (if discoverable) |
| Type | Category: Charter Company, Individual Operator, Fishing Charter, Sailboat Operator, Rental Company, Yacht Charter, Watersports Operator |
| Checked? | Leave blank — for the sales rep to mark after outreach |
| Boat Type | Types of boats offered (e.g., Pontoon, Center Console, Sailboat, Yacht, Catamaran, Jet Ski, etc.) |
| Boat Count | Number of boats in fleet (if discoverable) |
| Activities/Events/Services | What they offer: fishing trips, sunset cruises, party boats, watersports, diving, snorkeling, etc. |
| Phone Number | Business phone — **REQUIRED if Email is blank** (every operator must have Phone OR Email) |
| Email | Business email — **REQUIRED if Phone Number is blank** (every operator must have Phone OR Email) |
| Booking Software | What booking system they use (e.g., FareHarbor, Peek, Bookeo, own website, etc.) |
| Already on Boatsetter? | Yes/No/Unknown — leave blank if unsure, admin will verify post-run (Boatsetter uses boat IDs that are hard to search) |
| Boatsetter Link | Leave blank — admin will populate after manual verification |
| Already on GMB? | Yes/No/Unknown — leave blank if unsure, admin will verify post-run (Getmyboat uses boat IDs that are hard to search) |
| GMB Link | Leave blank — admin will populate after manual verification |
| Listing URL | The BEST external link found for this operator. Priority order: (1) their own website, (2) FishingBooker listing, (3) any other 3rd-party listing (Viator, TripAdvisor, Yelp, BoatBooker, etc.). Only one link — pick the most useful one. |
| Found Via | Where this operator was first discovered: Google, FishingBooker, Viator, TripAdvisor, Yelp, BoatBooker, direct search, etc. |
| Website | **REQUIRED** — Business website URL (their own domain). If the operator has no standalone website, use their Facebook page URL instead. Every operator MUST have a link here; a Facebook page is an acceptable fallback, but this column must never be blank. |
| Location | City and specific marina/dock if known |
| State | US State |
| Social Handles | Instagram, Facebook, TikTok handles |

### Column Notes

- **Boatsetter / GMB columns**: Do NOT spend time searching boatsetter.com or getmyboat.com to
  verify listings. Both platforms use internal boat IDs in their URLs, making it unreliable to
  search by operator name. Leave "Already on Boatsetter?" and "Already on GMB?" as blank/Unknown.
  The admin team will update these columns after the skill runs using their internal admin tools.
- **Listing URL**: This is the single best 3rd-party link for each operator. Prioritize in this order:
  1. Their own website (if they have one)
  2. FishingBooker profile (great for fishing charters)
  3. Any other 3rd-party listing: Viator, TripAdvisor, Yelp, BoatBooker, Google Maps, etc.
  Only include ONE link here — the most useful/authoritative one.
- **Website vs Listing URL**: If the operator has their own website, put it in BOTH "Website" and
  "Listing URL". If they have no standalone website, the "Website" column must still be populated —
  use their Facebook page URL as the fallback. "Website" is never allowed to be blank.
- **Mandatory contact rule**: Every operator row MUST have at least one of Phone Number OR Email.
  If you cannot find either after checking the operator's website, Facebook page, FishingBooker/Viator/
  TripAdvisor listing, and Google Maps profile, DO NOT include that operator in the final spreadsheet.
- **Mandatory link rule**: Every operator row MUST have a value in the "Website" column. A Facebook
  page URL is an acceptable substitute when no standalone website exists. If neither a website nor a
  Facebook page can be found, DO NOT include that operator in the final spreadsheet.

### Column Grouping Logic

The spreadsheet groups columns into logical sections:
- **Operator Info** (Charter Name → Activities/Events/Services)
- **Contact** (Phone Number, Email)
- **Tech** (Booking Software)
- **Platform Presence** (Already on Boatsetter?, Boatsetter Link, Already on GMB?, GMB Link, Listing URL)
- **Discovery** (Found Via)
- **Identity** (Website, Location, State, Social Handles)

## DMA-Based Search Strategy

The user provides a DMA name (e.g., "Tampa-St. Petersburg (Sarasota)" or "Miami-Fort Lauderdale").
The skill must decompose that DMA into its constituent cities, coastal towns, lakes, rivers, and
waterways, then systematically search each sub-area.

### Step 1: Decompose the DMA

When you receive a DMA, identify ALL water-accessible areas within it:

1. **Coastal cities and towns** — every town with ocean, bay, gulf, or sound access
2. **Lake communities** — towns on significant lakes
3. **River towns** — towns on navigable rivers
4. **Marina clusters** — known marina districts or harbor areas
5. **Island communities** — barrier islands, keys, etc.

Create a search plan listing every sub-area before beginning searches.

### Step 2: Systematic Search Queries

For EACH sub-area identified, run web searches using these query patterns. Vary the queries to
maximize coverage — different operators rank for different terms:

**Primary queries (run for every sub-area):**
- `boat rental [city/area]`
- `fishing charter [city/area]`
- `boat charter [city/area]`
- `sailboat rental [city/area]`
- `yacht charter [city/area]`
- `pontoon rental [city/area]`
- `jet ski rental [city/area]`
- `boat tour [city/area]`
- `sunset cruise [city/area]`
- `party boat [city/area]`

**Secondary queries (run for larger cities or known boating hubs):**
- `boat rental near [marina name]`
- `watersports rental [city/area]`
- `catamaran charter [city/area]`
- `deep sea fishing [city/area]`
- `inshore fishing charter [city/area]`

**3rd-party platform queries (critical for finding operators who may not rank well in Google):**

FishingBooker — major source for fishing charters:
- `site:fishingbooker.com [city/area]`
- `fishingbooker.com [city/area] fishing charter`

Viator — major OTA with tour/charter operators:
- `site:viator.com [city/area] boat`
- `viator.com [city/area] boat tour`
- `viator.com [city/area] fishing`

TripAdvisor — reviews AND bookable experiences:
- `site:tripadvisor.com [city/area] boat rental`
- `site:tripadvisor.com [city/area] fishing charter`
- `site:tripadvisor.com [city/area] boat tour`

Google / Yelp (organic discovery):
- `boat rental companies [city/area] site:yelp.com`
- `[city/area] boat rental site:google.com/maps`

BoatBooker — yacht charters and higher-end rentals:
- `site:boatbooker.com [city/area]`

### Step 2b: Platform Deep Scrape

After running initial searches, do a DEDICATED PASS through FishingBooker, Viator, and TripAdvisor
to catch operators that don't rank in Google but ARE listed on these platforms:

**FishingBooker scrape:**
1. Search `fishingbooker.com/charter/[city]` and `fishingbooker.com/destinations/[city]`
2. web_fetch each results page to extract all listed captains/charters
3. For each listing, capture: captain name, boat name, boat type, trip types
4. Cross-reference against your master list — any new operators get added

**Viator scrape:**
1. Search `viator.com/[city]/boat-tours` and `viator.com/[city]/fishing`
2. web_fetch results pages to extract all experience providers
3. Note: Viator operators often use trade names different from their legal business name —
   try to identify the underlying charter company

**TripAdvisor scrape:**
1. Search `tripadvisor.com/Attractions-[city]-Boat_Tours_Water_Sports`
2. web_fetch results pages to extract all listed operators
3. TripAdvisor is excellent for finding small independent operators who may not be on
   any booking platform — these are HIGH VALUE prospects

**Google Maps / Google Search:**
1. Search `boat charter near [city]` and `fishing charter near [city]`
2. Pay attention to Google Maps pack results (the local 3-pack)
3. Capture: business name, phone, website, address

### Step 3: Data Extraction

For each operator found, extract as much information as possible:

1. **Visit their website** (web_fetch) to get:
   - Business name and owner name (check "About Us" pages)
   - Phone number and email — **at least one of these is required for the operator to be included**
   - Boat types and fleet size
   - Services offered
   - Social media links (usually in footer or header) — **capture the Facebook URL specifically, as
     it may be needed as the fallback for the "Website" column**
   - What booking software they use (check the booking flow URL patterns):
     - FareHarbor: URLs contain `fareharbor.com`
     - Peek: URLs contain `peek.com`
     - Bookeo: URLs contain `bookeo.com`
     - Rezdy: URLs contain `rezdy.com`
     - Checkfront: URLs contain `checkfront.com`
     - Square: URLs contain `squareup.com` or `square.site`
     - Xola: URLs contain `xola.com`
     - If booking is just email/phone, note "Direct booking only"

2. **Build the Listing URL** — pick the single best link for this operator:
   - If they have their own website → use that
   - If no website but on FishingBooker → use FishingBooker link
   - If no website and not on FishingBooker → use whichever 3rd-party link you found
     (Viator, TripAdvisor, Yelp, BoatBooker, Google Maps, etc.)

2b. **Populate the Website column (mandatory)**:
   - If the operator has a standalone website, use it.
   - If they do NOT have a standalone website, use their Facebook page URL as the fallback.
   - The "Website" column must NEVER be blank. If neither a website nor a Facebook page can be
     found after a thorough search, drop the operator from the spreadsheet.

3. **Do NOT search Boatsetter or Getmyboat** for individual operators. Both platforms use
   internal boat IDs making name-based searches unreliable. Leave those columns blank/Unknown.
   Admin will update post-run.

4. **Filter out incomplete records before writing the spreadsheet.** An operator is only included
   if BOTH of the following are true:
   - They have at least one of Phone Number OR Email
   - They have a value for the Website column (standalone website OR Facebook page)
   Operators that fail either check are dropped from the final output.

5. **Deduplicate** — same business may appear under different names across sites:
   - "Captain Mike's Fishing" on their website = "Mike's Deep Sea Adventures" on Viator
   - Individual captains may list on FishingBooker under personal name but have a company name
     on their own website
   - Cross-reference by: phone number, address, captain name, boat name

### Step 4: Generate the Spreadsheet

Use the xlsx skill (read `/mnt/skills/public/xlsx/SKILL.md`) to create a professionally formatted
spreadsheet with:

- Header row with bold white text on dark navy (#1B3A5C) background
- **Column group headers** (row above the main headers) with merged cells:
  - "OPERATOR INFO" spanning Charter Name → Activities/Events/Services (light navy #2C5F8A)
  - "CONTACT" spanning Phone Number → Email (dark teal #1A6B5C)
  - "TECH" over Booking Software (slate #4A5568)
  - "PLATFORM PRESENCE" spanning Already on Boatsetter? → Listing URL (dark orange #C2590A)
  - "DISCOVERY" over Found Via (purple #5B21B6)
  - "IDENTITY" spanning Website → Social Handles (dark green #166534)
- Alternating row colors (white / light blue #E8F0FE)
- Auto-fitted column widths
- Frozen top 2 rows (group header + column headers)
- Data validation dropdown for "Type" column
- Data validation dropdowns for "Already on Boatsetter?" and "Already on GMB?" (Yes/No/Unknown)
- Hyperlinks for Listing URL and Website columns
- Filter arrows on all column headers

**Summary sheet** with:
  - Total operators found
  - Breakdown by Type
  - Breakdown by Found Via (shows which sources yielded the most leads)
  - DMA searched
  - Date of search
  - Sub-areas covered

### Step 5: Completeness Check

Before delivering, verify coverage by checking:
- Did you search every coastal/waterfront city in the DMA?
- Did you find operators from Google Maps, Yelp, TripAdvisor, and direct searches?
- Did you scrape FishingBooker for all fishing charter operators in the area?
- Did you check Viator for boat tour and charter experience providers?
- Did you check TripAdvisor for boat tour and charter listings?
- Did you check BoatBooker for yacht/rental operators?
- Are there any well-known marinas in the area you haven't searched?

**Mandatory-field audit (run this right before export):**
- Every row has either a Phone Number or an Email — no row has both blank.
- Every row has a value in the Website column (standalone website OR Facebook page).
- Any row that fails either check is removed from the final spreadsheet.

## Important Notes

- **Do not stop until the entire DMA is covered.** DMAs can be large. Work through every sub-area
  methodically. If the DMA has 30 waterfront towns, search all 30.
- **Err on the side of inclusion.** If an operator might be relevant, include them. The sales team
  can filter later.
- **Mark unknowns honestly.** If you can't find an owner name or phone number, leave it blank rather
  than guessing.
- **Do NOT waste time verifying Boatsetter/Getmyboat presence.** Admin handles that post-run.
- **Track your progress.** As you work through sub-areas, keep a running list so you don't miss any
  or duplicate effort.
- **Batch your searches efficiently.** Group nearby areas and use broader searches when appropriate,
  but always follow up with specific local searches.

## DMA Reference

There are 210 DMAs in the US. The user may specify by:
- Full name: "Tampa-St. Petersburg (Sarasota)"
- Short name: "Tampa" or "Tampa Bay"
- DMA number: "539" (Nielsen code)
- Region: "South Florida" (map to appropriate DMA(s))

Common boating-heavy DMAs include:
- Miami-Fort Lauderdale (#528)
- Tampa-St. Petersburg-Sarasota (#539)
- West Palm Beach-Fort Pierce (#548)
- Jacksonville (#561)
- Orlando-Daytona Beach (#534)
- San Diego (#825)
- Los Angeles (#803)
- San Francisco-Oakland-San Jose (#807)
- Seattle-Tacoma (#819)
- New York (#501)
- Boston (#506)
- Charleston (#519)
- Savannah (#507)
- Myrtle Beach-Florence (#570)
- Norfolk-Portsmouth-Newport News (#544)
- Baltimore (#512)
- Honolulu (#744)
- Mobile-Pensacola (#686)
- New Orleans (#622)
- Houston (#618)
- Chicago (#602)
- Detroit (#505)
- Cleveland (#510)
- Minneapolis-St. Paul (#613)
- Nashville (#659)

If the user provides an ambiguous name, ask for clarification.

## Output

The final deliverable is a single .xlsx file named:
`[DMA_Name]_Boat_Charter_Prospects_[YYYY-MM-DD].xlsx`

Example: `Tampa_Bay_Boat_Charter_Prospects_2026-04-07.xlsx`

Save to `/mnt/user-data/outputs/` and present to the user.