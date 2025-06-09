223
224
225
226
227
228
229
230
231
232
233
234
235
236
237
238
239
240
241
242
243
244
245
246
247
248
249
250
251
252
253
254
255
256
257
258
259
260
261
262
263
264
265
266
267
268
269
270
271
272
273
274
275
276
277
278
279
280
281
282
283
284
285
286
287
288
289
290
291
292
293
294
295
296
297
298
299
300
301

        "postedTo": end_date.strftime("%m/%d/%Y"),
        "ptype": "o",
        "limit": 50
    }
    if keyword:
        sam_params["keyword"] = keyword
    if naics:
        sam_params["naics"] = naics
    
    usa_payload = {
        "filters": {
            "time_period": [{"start_date": start_date.strftime("%Y-%m-%d"), "end_date": end_date.strftime("%Y-%m-%d")}],
            "award_type_codes": ["A", "B", "C", "D"]
        },
        "fields": ["award_id", "recipient_name", "naics_code", "action_date", "awarding_agency_name"],
        "limit": 50,
        "page": 1,
        "sort": "-action_date"
    }
    if keyword:
        usa_payload["filters"]["keywords"] = [keyword]
    if naics:
        usa_payload["filters"]["naics_codes"] = [naics]
    
    try:
        with database_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM opportunities")
            cursor.execute("DELETE FROM awards")
            conn.commit()
        
        sam_data = fetch_sam_data(sam_params)
        store_opportunities(sam_data)
        
        usa_data = fetch_usa_data(usa_payload)
        store_awards(usa_data)
        
        logger.info("Data fetch and store completed successfully")
    except Exception as e:
        logger.error(f"Data fetch failed: {e}")
        raise

def schedule_jobs():
    """Setup scheduled jobs"""
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        fetch_and_store_data,
        'interval',
        hours=24,
        next_run_time=current_datetime  # Start immediately at the specified time
    )
    scheduler.start()
    logger.info("Scheduled jobs initialized")

@app.route('/')
def home():
    """Render the home page with opportunities and awards"""
    try:
        with database_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM opportunities ORDER BY date DESC")
            opportunities = [dict(row) for row in cursor.fetchall()]
            cursor.execute("SELECT * FROM awards ORDER BY date DESC")
            awards = [dict(row) for row in cursor.fetchall()]
        return render_template('home.html', opportunities=opportunities, awards=awards)
    except sqlite3.Error as e:
        logger.error(f"Database query failed: {e}")
        return "Error loading data. Check logs.", 500

if __name__ == "__main__":
    try:
        setup_database()
        schedule_jobs()
        port = int(os.getenv("PORT", 5000))  # Use Render's PORT or default to 5000
        app.run(debug=True, host='0.0.0.0', port=port)
    except Exception as e:
        logger.error(f"Application initialization failed: {e}")
        raise

Use Control + Shift + m to toggle the tab key moving focus. Alternatively, use esc then tab to move to the next interactive element on the page.
