# Sources Page Test Plan

## Overview
This document outlines the comprehensive test plan for the Sources page of the Huntable CTI Studio application. The Sources page allows users to manage and monitor threat intelligence collection sources.

**Page URL:** `/sources`  
**Base URL:** `http://localhost:8001` (or `CTI_SCRAPER_URL` environment variable)

---

## 1. Page Load and Navigation Tests

### 1.1 Sources Page Loads Successfully
- **Test ID:** SOURCES-001
- **Description:** Verify the sources page loads without errors
- **Steps:**
  1. Navigate to `/sources`
  2. Wait for `networkidle` load state
- **Expected Results:**
  - Page returns HTTP 200
  - No critical console errors
- **Success Criteria:** Page loads successfully

### 1.2 Page Title Verification
- **Test ID:** SOURCES-002
- **Description:** Verify correct page title is displayed
- **Steps:**
  1. Navigate to `/sources`
  2. Wait for load
- **Expected Results:** Page title contains "Sources - Huntable CTI Studio"
- **Success Criteria:** Title matches expected text

### 1.3 Main Heading Display
- **Test ID:** SOURCES-003
- **Description:** Verify main page heading is visible
- **Steps:**
  1. Navigate to `/sources`
  2. Wait for load
- **Expected Results:** Heading "Threat Intelligence Sources" is visible
- **Success Criteria:** Heading element is present and visible

### 1.4 Breadcrumb Navigation
- **Test ID:** SOURCES-004
- **Description:** Verify breadcrumb navigation works correctly
- **Steps:**
  1. Navigate to `/sources`
  2. Wait for load
  3. Locate breadcrumb navigation
  4. Click "Home" link
- **Expected Results:**
  - Breadcrumb shows "Home" > "Sources" path
  - Clicking Home navigates to `/`
- **Success Criteria:** Navigation to home page works correctly

---

## 2. Source List Display Tests

### 2.1 Configured Sources Section
- **Test ID:** SOURCES-010
- **Description:** Verify "Configured Sources" section header is displayed
- **Steps:**
  1. Navigate to `/sources`
  2. Wait for load
- **Expected Results:** Section header "🔗 Configured Sources" is visible
- **Success Criteria:** Header element exists

### 2.2 Source Sorting Indicator
- **Test ID:** SOURCES-011
- **Description:** Verify sources are sorted by hunt score
- **Steps:**
  1. Navigate to `/sources`
  2. Wait for load
- **Expected Results:** Sort indicator shows "Sorted by: Hunt Score (highest first)"
- **Success Criteria:** Sort indicator text is correct

### 2.3 Source Card Display
- **Test ID:** SOURCES-012
- **Description:** Verify source cards display correctly when sources exist
- **Steps:**
  1. Navigate to `/sources`
  2. Wait for load
  3. Locate source cards (if any)
- **Expected Results:**
  - Source cards have proper styling with hover effects
  - Each card contains source name, URL, status badge
- **Success Criteria:** Cards render with all expected elements

### 2.4 Source Article Count Badge
- **Test ID:** SOURCES-013
- **Description:** Verify article count badges display on source cards
- **Steps:**
  1. Navigate to `/sources`
  2. Wait for load
  3. Find article count badges
- **Expected Results:** Each source shows a badge with article count (e.g., "42")
- **Success Criteria:** Badge displays numeric count

### 2.5 Source Name Links
- **Test ID:** SOURCES-014
- **Description:** Verify source names link to articles filtered by source
- **Steps:**
  1. Navigate to `/sources`
  2. Wait for load
  3. Click any source name link
- **Expected Results:**
  - Link href follows pattern `/articles?source_id=<id>`
  - Clicking navigates to filtered articles page
- **Success Criteria:** Navigation to articles page works

### 2.6 Source Status Badges
- **Test ID:** SOURCES-015
- **Description:** Verify status badges show correct status (Active/Inactive)
- **Steps:**
  1. Navigate to `/sources`
  2. Wait for load
  3. Check status badges
- **Expected Results:**
  - Active sources show green "Active" badge
  - Inactive sources show red "Inactive" badge
- **Success Criteria:** Status badges reflect source status correctly

### 2.7 Source Metadata Fields
- **Test ID:** SOURCES-016
- **Description:** Verify all metadata fields display for each source
- **Steps:**
  1. Navigate to `/sources`
  2. Wait for load
  3. Check metadata display
- **Expected Results:** Each source displays:
  - URL
  - RSS Feed (if present)
  - Collection Method
  - Last Check timestamp
  - Articles Collected count
  - Check Frequency
  - Lookback Window
  - Min Content Length
- **Success Criteria:** All metadata fields visible

### 2.8 Empty State Display
- **Test ID:** SOURCES-017
- **Description:** Verify appropriate message when no sources configured
- **Steps:**
  1. Ensure no sources in database (or use test environment)
  2. Navigate to `/sources`
  3. Wait for load
- **Expected Results:** Shows "No sources configured" message with guidance
- **Success Criteria:** Empty state message displays correctly

### 2.9 Manual Source Panel
- **Test ID:** SOURCES-018
- **Description:** Verify Manual source panel displays correctly
- **Steps:**
  1. Navigate to `/sources`
  2. Wait for load
  3. Locate Manual Source panel (blue styled)
- **Expected Results:**
  - Panel header shows "📝 Manual Source"
  - Panel has distinct styling from regular sources
  - Shows Manual Entry collection method
- **Success Criteria:** Manual source panel renders correctly

---

## 3. Source Action Buttons Tests

### 3.1 Collect Now Button - Presence
- **Test ID:** SOURCES-020
- **Description:** Verify "Collect Now" button exists for each source
- **Steps:**
  1. Navigate to `/sources`
  2. Wait for load
  3. Find "Collect Now" buttons
- **Expected Results:** Button has 🚀 emoji and "Collect Now" text
- **Success Criteria:** Button visible with correct styling

### 3.2 Collect Now Button - API Call
- **Test ID:** SOURCES-021
- **Description:** Verify "Collect Now" triggers correct API call
- **Steps:**
  1. Navigate to `/sources`
  2. Wait for load
  3. Intercept API route `/api/sources/*/collect`
  4. Click "Collect Now" button
- **Expected Results:**
  - POST request sent to `/api/sources/{source_id}/collect`
  - Request contains source_id
- **Success Criteria:** API endpoint called correctly

### 3.3 Collection Status Display
- **Test ID:** SOURCES-022
- **Description:** Verify collection status panel appears during collection
- **Steps:**
  1. Navigate to `/sources`
  2. Click "Collect Now"
- **Expected Results:**
  - Collection status panel (#collectionStatus) becomes visible
  - Shows source name and progress
  - Contains terminal output area
  - Has close button
- **Success Criteria:** Status panel displays during collection

### 3.4 Configure Button - Presence
- **Test ID:** SOURCES-023
- **Description:** Verify "Configure" button exists for each source
- **Steps:**
  1. Navigate to `/sources`
  2. Wait for load
  3. Find "Configure" buttons
- **Expected Results:** Button has ⚙️ emoji and "Configure" text
- **Success Criteria:** Button visible with correct styling

### 3.5 Configure Button - Opens Modal
- **Test ID:** SOURCES-024
- **Description:** Verify clicking Configure opens configuration modal
- **Steps:**
  1. Navigate to `/sources`
  2. Wait for load
  3. Click "Configure" button
- **Expected Results:**
  - Configuration modal (#sourceConfigModal) becomes visible
  - Modal contains form fields
- **Success Criteria:** Modal opens correctly

### 3.6 Toggle Status Button - Presence
- **Test ID:** SOURCES-025
- **Description:** Verify "Toggle Status" button exists for each source
- **Steps:**
  1. Navigate to `/sources`
  2. Wait for load
  3. Find "Toggle Status" buttons
- **Expected Results:** Button has 🔄 emoji and "Toggle Status" text
- **Success Criteria:** Button visible with correct styling

### 3.7 Toggle Status Button - API Call
- **Test ID:** SOURCES-026
- **Description:** Verify "Toggle Status" triggers correct API call
- **Steps:**
  1. Navigate to `/sources`
  2. Wait for load
  3. Intercept API route `/api/sources/*/toggle`
  4. Click "Toggle Status" button
- **Expected Results:**
  - POST request sent to `/api/sources/{source_id}/toggle`
  - Request contains source_id
- **Success Criteria:** API endpoint called correctly

### 3.8 Toggle Status - Result Modal
- **Test ID:** SOURCES-027
- **Description:** Verify toggle status shows result in modal
- **Steps:**
  1. Navigate to `/sources`
  2. Click "Toggle Status"
  3. Wait for modal
- **Expected Results:**
  - Result modal (#resultModal) shows status change details
  - Shows old status and new status
  - Shows success message
- **Success Criteria:** Modal displays correct status change info

### 3.9 Stats Button - Presence
- **Test ID:** SOURCES-028
- **Description:** Verify "Stats" button exists for each source
- **Steps:**
  1. Navigate to `/sources`
  2. Wait for load
  3. Find "Stats" buttons
- **Expected Results:** Button has 📊 emoji and "Stats" text
- **Success Criteria:** Button visible with correct styling

### 3.10 Stats Button - API Call
- **Test ID:** SOURCES-029
- **Description:** Verify "Stats" triggers correct API call
- **Steps:**
  1. Navigate to `/sources`
  2. Wait for load
  3. Intercept API route `/api/sources/*/stats`
  4. Click "Stats" button
- **Expected Results:**
  - GET request sent to `/api/sources/{source_id}/stats`
- **Success Criteria:** API endpoint called correctly

### 3.11 Stats Modal - Content Display
- **Test ID:** SOURCES-030
- **Description:** Verify stats modal displays comprehensive statistics
- **Steps:**
  1. Navigate to `/sources`
  2. Click "Stats" button
  3. Wait for modal content
- **Expected Results:** Modal displays:
  - Source name
  - Status (Active/Inactive)
  - Collection method
  - Total articles
  - Average content length
  - Average threat hunting score
  - Last check timestamp
  - Recent activity (articles by date)
- **Success Criteria:** All statistics displayed correctly

### 3.12 Manual Source - Buttons Disabled
- **Test ID:** SOURCES-031
- **Description:** Verify Manual source has disabled Configure and Toggle buttons
- **Steps:**
  1. Navigate to `/sources`
  2. Find Manual source panel
  3. Check button states
- **Expected Results:**
  - Configure button is disabled or shows tooltip explaining disabled state
  - Toggle Status button is disabled
  - Only Stats button is enabled
- **Success Criteria:** Manual source cannot be configured or toggled

---

## 4. Source Configuration Modal Tests

### 4.1 Configuration Modal - Form Fields
- **Test ID:** SOURCES-040
- **Description:** Verify all configuration form fields exist
- **Steps:**
  1. Navigate to `/sources`
  2. Click "Configure" on any source
  3. Check form fields
- **Expected Results:** Three input fields:
  - Lookback Window (days) - #configLookbackDays
  - Check Frequency (minutes) - #configCheckFrequency
  - Minimum Content Length - #configMinContentLength
- **Success Criteria:** All fields present

### 4.2 Configuration Modal - Input Constraints
- **Test ID:** SOURCES-041
- **Description:** Verify input fields have correct validation constraints
- **Steps:**
  1. Open configuration modal
  2. Check HTML attributes
- **Expected Results:**
  - Lookback: min=1, max=365
  - Check Frequency: min=1, max=1440
  - Min Content Length: min=0
- **Success Criteria:** Constraints match requirements

### 4.3 Configuration Modal - Current Values Loaded
- **Test ID:** SOURCES-042
- **Description:** Verify current source values pre-populate the form
- **Steps:**
  1. Open configuration modal
  2. Check input values
- **Expected Results:** Form fields show current source configuration values
- **Success Criteria:** Values match source settings

### 4.4 Configuration Modal - Save Button
- **Test ID:** SOURCES-043
- **Description:** Verify Save button exists and has correct text
- **Steps:**
  1. Open configuration modal
  2. Find save button
- **Expected Results:** Button shows "Save Changes"
- **Success Criteria:** Button displays correctly

### 4.5 Configuration Modal - Cancel Button
- **Test ID:** SOURCES-044
- **Description:** Verify Cancel button closes modal
- **Steps:**
  1. Open configuration modal
  2. Click Cancel button
- **Expected Results:** Modal closes (adds "hidden" class)
- **Success Criteria:** Modal closes on cancel

### 4.6 Configuration Modal - Click Outside Closes
- **Test ID:** SOURCES-045
- **Description:** Verify clicking outside modal closes it
- **Steps:**
  1. Open configuration modal
  2. Click on backdrop/outside area
- **Expected Results:** Modal closes
- **Success Criteria:** Click-away closes modal

### 4.7 Configuration Modal - Escape Key Closes
- **Test ID:** SOURCES-046
- **Description:** Verify pressing Escape closes modal
- **Steps:**
  1. Open configuration modal
  2. Press Escape key
- **Expected Results:** Modal closes
- **Success Criteria:** Escape key closes modal

### 4.8 Configuration Modal - API Calls on Save
- **Test ID:** SOURCES-047
- **Description:** Verify save triggers all three API endpoints
- **Steps:**
  1. Open configuration modal
  2. Fill form with valid values
  3. Intercept API routes
  4. Click Save
- **Expected Results:** Three API calls made:
  - PUT `/api/sources/{id}/lookback`
  - PUT `/api/sources/{id}/check_frequency`
  - PUT `/api/sources/{id}/min_content_length`
- **Success Criteria:** All three endpoints called

### 4.9 Configuration Modal - Validation Errors
- **Test ID:** SOURCES-048
- **Description:** Verify form validation shows errors for invalid input
- **Steps:**
  1. Open configuration modal
  2. Enter invalid values (e.g., lookback > 365)
  3. Attempt to save
- **Expected Results:** Error notification appears
- **Success Criteria:** Validation prevents invalid save

---

## 5. Manual URL Scraping Tests

### 5.1 URL Scraping Section - Display
- **Test ID:** SOURCES-050
- **Description:** Verify manual URL scraping section is visible
- **Steps:**
  1. Navigate to `/sources`
  2. Wait for load
- **Expected Results:** Section header "Manual URL Scraping" is visible
- **Success Criteria:** Section displays correctly

### 5.2 URL Scraping Form - URL Textarea
- **Test ID:** SOURCES-051
- **Description:** Verify URL textarea accepts multiple URLs
- **Steps:**
  1. Navigate to `/sources`
  2. Find URL textarea (#adhocUrl)
- **Expected Results:**
  - Textarea is present
  - Accepts multiple URLs (one per line)
  - Has required attribute
- **Success Criteria:** Textarea functional

### 5.3 URL Scraping Form - Title Input
- **Test ID:** SOURCES-052
- **Description:** Verify optional title input field exists
- **Steps:**
  1. Navigate to `/sources`
  2. Find title input (#adhocTitle)
- **Expected Results:** Input field present with placeholder "Leave empty to auto-detect"
- **Success Criteria:** Title field present

### 5.4 URL Scraping Form - Force Scrape Checkbox
- **Test ID:** SOURCES-053
- **Description:** Verify force scrape checkbox exists
- **Steps:**
  1. Navigate to `/sources`
  2. Find force scrape checkbox (#adhocForceScrape)
- **Expected Results:** Checkbox present with label about overriding duplicate URL check
- **Success Criteria:** Checkbox functional

### 5.5 URL Scraping Button
- **Test ID:** SOURCES-054
- **Description:** Verify scrape button exists and has correct text
- **Steps:**
  1. Navigate to `/sources`
  2. Find scrape button (#scrapeUrlBtn)
- **Expected Results:** Button shows "🔍 Scrape URLs"
- **Success Criteria:** Button displays correctly

### 5.6 URL Scraping - API Call
- **Test ID:** SOURCES-055
- **Description:** Verify scraping URLs triggers correct API
- **Steps:**
  1. Navigate to `/sources`
  2. Enter valid URL(s)
  3. Intercept API route `/api/scrape-url`
  4. Click "Scrape URLs"
- **Expected Results:**
  - POST request sent to `/api/scrape-url`
  - Request body contains urls array
- **Success Criteria:** API called correctly

### 5.7 URL Scraping - Status Display
- **Test ID:** SOURCES-056
- **Description:** Verify scraping status shows during process
- **Steps:**
  1. Navigate to `/sources`
  2. Submit URLs
  3. Check status display
- **Expected Results:** Status panel (#scrapingStatus) shows progress
- **Success Criteria:** Status displays during scraping

### 5.8 URL Scraping - URL Validation
- **Test ID:** SOURCES-057
- **Description:** Verify invalid URLs are rejected
- **Steps:**
  1. Navigate to `/sources`
  2. Enter invalid URLs (e.g., "not-a-url")
  3. Attempt to submit
- **Expected Results:** Error notification appears
- **Success Criteria:** Invalid URLs rejected with error message

### 5.9 URL Scraping - Empty Submission
- **Test ID:** SOURCES-058
- **Description:** Verify empty URL field shows validation error
- **Steps:**
  1. Navigate to `/sources`
  2. Leave URL textarea empty
  3. Click "Scrape URLs"
- **Expected Results:** Error message "Please enter at least one URL"
- **Success Criteria:** Validation prevents empty submission

### 5.10 URL Scraping - Success Notification
- **Test ID:** SOURCES-059
- **Description:** Verify successful scraping shows success notification
- **Steps:**
  1. Submit valid URLs for scraping
  2. Wait for completion
- **Expected Results:** Success notification with details of scraped URLs
- **Success Criteria:** Success message displays

---

## 6. PDF Upload Section Tests

### 6.1 PDF Upload Section - Display
- **Test ID:** SOURCES-060
- **Description:** Verify PDF upload section is visible
- **Steps:**
  1. Navigate to `/sources`
  2. Wait for load
- **Expected Results:** Section shows "📄 Upload PDF Reports" header
- **Success Criteria:** Section displays correctly

### 6.2 PDF Upload Button - Link
- **Test ID:** SOURCES-061
- **Description:** Verify upload PDF button links to correct page
- **Steps:**
  1. Navigate to `/sources`
  2. Click "Upload PDF" link
- **Expected Results:** Navigates to `/pdf-upload`
- **Success Criteria:** Navigation works correctly

---

## 7. Database Status Banner Tests

### 7.1 Database Status Banner - Initially Hidden
- **Test ID:** SOURCES-070
- **Description:** Verify database status banner is hidden by default
- **Steps:**
  1. Navigate to `/sources`
  2. Wait for load
- **Expected Results:** Banner (#dbStatusBanner) has "hidden" class
- **Success Criteria:** Banner not visible initially

### 7.2 Database Status Banner - Refresh Button
- **Test ID:** SOURCES-071
- **Description:** Verify banner has working refresh button
- **Steps:**
  1. Navigate to `/sources`
  2. Make banner visible (simulate error condition)
  3. Click refresh button
- **Expected Results:** Page reloads
- **Success Criteria:** Refresh button functional

---

## 8. Result Modal Tests

### 8.1 Result Modal - Initially Hidden
- **Test ID:** SOURCES-080
- **Description:** Verify result modal is hidden by default
- **Steps:**
  1. Navigate to `/sources`
  2. Wait for load
- **Expected Results:** Modal (#resultModal) has "hidden" class
- **Success Criteria:** Modal not visible initially

### 8.2 Result Modal - Close Button
- **Test ID:** SOURCES-081
- **Description:** Verify result modal has working close button
- **Steps:**
  1. Trigger an action that shows modal
  2. Click Close button
- **Expected Results:** Modal closes
- **Success Criteria:** Close button functional

### 8.3 Result Modal - Title and Content
- **Test ID:** SOURCES-082
- **Description:** Verify modal displays correct title and content
- **Steps:**
  1. Trigger an action (e.g., toggle status)
  2. Check modal content
- **Expected Results:**
  - Title element (#modalTitle) shows appropriate title
  - Content element (#modalContent) shows details
- **Success Criteria:** Content displays correctly

---

## 9. API Endpoint Tests

### 9.1 GET /api/sources - List All Sources
- **Test ID:** SOURCES-090
- **Description:** Verify API returns list of all sources
- **Steps:**
  1. Send GET request to `/api/sources`
- **Expected Results:**
  - Returns 200 status
  - Response contains "sources" array
  - Each source has expected fields
- **Success Criteria:** API returns correct data

### 9.2 GET /api/sources/{source_id} - Get Single Source
- **Test ID:** SOURCES-091
- **Description:** Verify API returns specific source
- **Steps:**
  1. Send GET request to `/api/sources/1` (or valid ID)
- **Expected Results:**
  - Returns 200 status
  - Response contains source details
- **Success Criteria:** API returns correct source

### 9.3 GET /api/sources/{source_id}/stats - Get Source Stats
- **Test ID:** SOURCES-092
- **Description:** Verify API returns source statistics
- **Steps:**
  1. Send GET request to `/api/sources/1/stats`
- **Expected Results:** Returns statistics including:
  - source_id, source_name, active status
  - collection_method, total_articles
  - avg_content_length, avg_threat_hunting_score
  - last_check, articles_by_date
- **Success Criteria:** Stats API returns comprehensive data

### 9.4 POST /api/sources/{source_id}/toggle - Toggle Status
- **Test ID:** SOURCES-093
- **Description:** Verify toggle API changes source status
- **Steps:**
  1. Send POST request to `/api/sources/1/toggle`
- **Expected Results:**
  - Returns 200 status
  - Response contains success: true
  - Shows old_status and new_status
- **Success Criteria:** Toggle works correctly

### 9.5 PUT /api/sources/{source_id}/lookback - Update Lookback
- **Test ID:** SOURCES-094
- **Description:** Verify lookback window can be updated
- **Steps:**
  1. Send PUT request to `/api/sources/1/lookback` with `{"lookback_days": 30}`
- **Expected Results:**
  - Returns 200 status
  - Returns success: true
- **Success Criteria:** Update works correctly

### 9.6 PUT /api/sources/{source_id}/check_frequency - Update Frequency
- **Test ID:** SOURCES-095
- **Description:** Verify check frequency can be updated
- **Steps:**
  1. Send PUT request to `/api/sources/1/check_frequency` with `{"check_frequency": 3600}`
- **Expected Results:**
  - Returns 200 status
  - Returns success: true
- **Success Criteria:** Update works correctly

### 9.7 PUT /api/sources/{source_id}/min_content_length - Update Min Length
- **Test ID:** SOURCES-096
- **Description:** Verify min content length can be updated
- **Steps:**
  1. Send PUT request to `/api/sources/1/min_content_length` with `{"min_content_length": 500}`
- **Expected Results:**
  - Returns 200 status
  - Returns success: true
- **Success Criteria:** Update works correctly

### 9.8 POST /api/sources/{source_id}/collect - Trigger Collection
- **Test ID:** SOURCES-097
- **Description:** Verify collection can be triggered manually
- **Steps:**
  1. Send POST request to `/api/sources/1/collect`
- **Expected Results:**
  - Returns 200 status
  - Response contains success: true and task_id
- **Success Criteria:** Collection triggered successfully

---

## 10. Edge Case Tests

### 10.1 Non-existent Source - Stats
- **Test ID:** SOURCES-100
- **Description:** Verify proper error for non-existent source stats
- **Steps:**
  1. Send GET request to `/api/sources/99999/stats`
- **Expected Results:** Returns 404 status with "Source not found"
- **Success Criteria:** Appropriate error handling

### 10.2 Invalid Source ID - Toggle
- **Test ID:** SOURCES-101
- **Description:** Verify proper error for non-existent source toggle
- **Steps:**
  1. Send POST request to `/api/sources/99999/toggle`
- **Expected Results:** Returns 404 status with "Source not found"
- **Success Criteria:** Appropriate error handling

### 10.3 Invalid Lookback Value - Too Low
- **Test ID:** SOURCES-102
- **Description:** Verify validation rejects lookback < 1
- **Steps:**
  1. Send PUT request with `{"lookback_days": 0}`
- **Expected Results:** Returns 400 status with validation error
- **Success Criteria:** Validation works

### 10.4 Invalid Lookback Value - Too High
- **Test ID:** SOURCES-103
- **Description:** Verify validation rejects lookback > 365
- **Steps:**
  1. Send PUT request with `{"lookback_days": 400}`
- **Expected Results:** Returns 400 status with validation error
- **Success Criteria:** Validation works

### 10.5 Invalid Check Frequency - Too Low
- **Test ID:** SOURCES-104
- **Description:** Verify validation rejects check_frequency < 60
- **Steps:**
  1. Send PUT request with `{"check_frequency": 30}`
- **Expected Results:** Returns 400 status with validation error
- **Success Criteria:** Validation works

### 10.6 Invalid Min Content Length - Negative
- **Test ID:** SOURCES-105
- **Description:** Verify validation rejects negative min_content_length
- **Steps:**
  1. Send PUT request with `{"min_content_length": -1}`
- **Expected Results:** Returns 400 status with validation error
- **Success Criteria:** Validation works

### 10.7 Missing Required Fields
- **Test ID:** SOURCES-106
- **Description:** Verify API handles missing required fields
- **Steps:**
  1. Send PUT request without required fields
- **Expected Results:** Returns 400 status with appropriate error
- **Success Criteria:** Error handling works

---

## 11. Responsive Design Tests

### 11.1 Mobile View - Source Cards Stack
- **Test ID:** SOURCES-110
- **Description:** Verify source cards stack vertically on mobile
- **Steps:**
  1. Set viewport to mobile size (375x667)
  2. Navigate to `/sources`
- **Expected Results:** Source cards stack in single column
- **Success Criteria:** Layout responsive

### 11.2 Mobile View - Configuration Modal
- **Test ID:** SOURCES-111
- **Description:** Verify configuration modal fits on mobile
- **Steps:**
  1. Set viewport to mobile size
  2. Open configuration modal
- **Expected Results:** Modal fits within viewport
- **Success Criteria:** Modal usable on mobile

---

## 12. Accessibility Tests

### 12.1 ARIA Labels on Buttons
- **Test ID:** SOURCES-120
- **Description:** Verify action buttons have ARIA labels
- **Steps:**
  1. Navigate to `/sources`
  2. Check button ARIA labels
- **Expected Results:** Buttons have descriptive aria-label attributes
- **Success Criteria:** Accessibility attributes present

### 12.2 Keyboard Navigation
- **Test ID:** SOURCES-121
- **Description:** Verify page is keyboard navigable
- **Steps:**
  1. Navigate to `/sources`
  2. Use Tab key to navigate
- **Expected Results:** Focus moves logically through interactive elements
- **Success Criteria:** Keyboard navigation works

### 12.3 Focus Management in Modals
- **Test ID:** SOURCES-122
- **Description:** Verify modals manage focus correctly
- **Steps:**
  1. Open a modal
  2. Check focus position
- **Expected Results:** Focus trapped within modal
- **Success Criteria:** Focus management works

---

## Test Data Requirements

### Preconditions
- Application running on test URL
- Database populated with test sources (or empty for empty state tests)
- Network intercept capability for API testing

### Test Users
- Standard user with access to Sources page
- No special permissions required

### Environment Variables
- `CTI_SCRAPER_URL`: Base URL for the application (default: `http://localhost:8001`)

---

## Test Execution Order

1. **Smoke Tests** (SOURCES-001 through SOURCES-003)
2. **Display Tests** (SOURCES-010 through SOURCES-018)
3. **Action Button Tests** (SOURCES-020 through SOURCES-031)
4. **Configuration Modal Tests** (SOURCES-040 through SOURCES-048)
5. **Manual URL Scraping Tests** (SOURCES-050 through SOURCES-059)
6. **PDF Upload Tests** (SOURCES-060 through SOURCES-061)
7. **Status Banner Tests** (SOURCES-070 through SOURCES-071)
8. **Result Modal Tests** (SOURCES-080 through SOURCES-082)
9. **API Tests** (SOURCES-090 through SOURCES-097)
10. **Edge Case Tests** (SOURCES-100 through SOURCES-106)
11. **Responsive Tests** (SOURCES-110 through SOURCES-111)
12. **Accessibility Tests** (SOURCES-120 through SOURCES-122)

---

## Success Criteria Summary

- All tests pass successfully
- No critical console errors during test execution
- All API endpoints return expected status codes
- All UI elements render correctly
- All user interactions produce expected results
- Error handling works correctly for edge cases
- Page is responsive across different viewport sizes
- Accessibility requirements are met
