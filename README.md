# SmartCart Solutions

A responsive Flask product-search demo that retrieves Amazon search results, calculates a 10% SmartCart commission, stores search/cache/commission records in MongoDB, downloads product images, and exports results to Excel. When Amazon omits prices from search cards, the scraper checks product detail pages before showing the item; products without a verified price are not displayed.

## Run locally

1. Install MongoDB Community Server and make sure its service is running. The app uses `mongodb://localhost:27017/` by default; set `MONGODB_URI` to use another MongoDB deployment.
2. Install the Python dependencies:

   ```powershell
   python -m pip install -r requirements.txt
   ```

3. Set the workbook identity in PowerShell so the exported filename matches the required `FirstName_LastName_RegistrationNumber.xlsx` format:

   ```powershell
   $env:SMARTCART_FIRST_NAME = "YourFirstName"
   $env:SMARTCART_LAST_NAME = "YourLastName"
   $env:SMARTCART_REGISTRATION_NUMBER = "YourRegistrationNumber"
   ```

4. Start the application from this folder:

   ```powershell
   python app.py
   ```

5. Open `http://127.0.0.1:5000` and search for a product. The Excel workbook is saved to the Windows Desktop and can also be downloaded from the results page. Product pictures are stored in `Online_Pictures/`. Click **Save commission log** on the results page to save the displayed list to MongoDB.

Amazon may return CAPTCHA, omit product prices, or block automated requests. In those cases, the app reports the issue and records the failed search in `search_history`; it does not calculate commissions from guessed prices or display fabricated data by default. For an explicitly labelled classroom demo fallback, set `$env:SMARTCART_USE_SAMPLE_IF_BLOCKED = "true"` before starting the app. Amazon does not reliably expose seller email addresses in public search results, so `Retailer_email` is `N/A`.

## MongoDB collections

- `products_cache`: normalized search term, saved products, and cache creation time. Results are considered fresh for 24 hours.
- `search_history`: every attempted search, timestamp, result count, and source (`cache`, `live`, `sample`, or `error`).
- `commission_log`: saved when you click **Save commission log** on the results page (searches are not logged automatically). Each entry holds the product list with every product's price, commission fee, total price and picture file name, plus list-level commission/value totals and source. The fee and total are recalculated on the server when saving. These are estimated commissions on search results, not completed-sale records.

## Assessment checklist

- [x] Accept a product name from the web form and use it as the search term.
- [x] Request Amazon search results remotely and handle blocked/failed requests.
- [x] Display product name, price, commission, total, rating, retailer, email availability, and saved picture name.
- [x] Calculate commission as 10% and total price as product price plus commission.
- [x] Connect to MongoDB and use `products_cache`, `search_history`, and `commission_log`.
- [x] Check the 24-hour MongoDB cache before searching Amazon.
- [x] Record each completed search, including cached and zero-result searches.
- [x] Save a returned list, including cached results, to `commission_log` on demand with the Save commission log button.
- [x] Export product results to an Excel workbook on the Desktop.
- [x] Save product images in `Online_Pictures/` (JPEG, PNG, WebP or GIF up to 5 MB) and reuse existing local image files.
- [x] Provide a responsive web page with accessible search controls, mobile-friendly product cards, and Excel download.
- [x] Handle blank input, MongoDB connection failure, Amazon failure, missing images, and Excel write failure.
- [ ] Replace the workbook identity defaults with your own first name, last name, and registration number before running the final demo.
- [ ] Verify MongoDB is running and test one live Amazon search in your network environment.
