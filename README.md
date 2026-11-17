# Stream Clipper

Paste a Twitch VOD link → get vertical (9:16), captioned short clips with titles, ready for
YouTube Shorts, Instagram Reels and X. Runs free on GitHub's cloud computers; nothing is downloaded to your PC.

## How it picks moments
1. Downloads **only the audio** of the stream (in the cloud).
2. Finds hype moments: sudden loud reactions (screaming, laughing) + the moments viewers already clipped on Twitch (official Twitch API, weighted by views).
3. Transcribes only those ~30 moments with Whisper (CPU, no graphics card needed).
4. Gemini (free API tier) judges each moment, trims it to 15–60 s with a strong hook, writes a title + caption.
5. Cuts just those seconds from the VOD and renders 1080×1920 video with bold word-by-word captions.

## One-time setup (about 15 minutes)
1. **Push this folder to a GitHub repo.** Public repos get unlimited free Actions minutes; private repos get 2,000 min/month (≈ 25–35 streams).
2. **Gemini API key (free):** https://aistudio.google.com/apikey → *Create API key*.
3. **Twitch API keys (free, optional but recommended):** https://dev.twitch.tv/console/apps → *Register Your Application* (OAuth redirect `http://localhost`, category *Other*) → copy Client ID, then *New Secret*.
4. In your GitHub repo: **Settings → Secrets and variables → Actions → New repository secret**, add:
   - `GEMINI_API_KEY`
   - `TWITCH_CLIENT_ID`
   - `TWITCH_CLIENT_SECRET`

Never paste these keys into chats, code or screenshots.

## Making clips
GitHub repo → **Actions** → **Make clips** → **Run workflow** → paste the VOD link → choose profile/layout → **Run**.
When it finishes (≈ 45–90 min for a 7 h stream), open the run and download the **clips-N** file under *Artifacts*.
The run summary shows every clip's title and caption (also in `POST-THESE.md`).

Twitch deletes VODs after 7–60 days, so clip within a day or two of the stream.

## Options
| Option | Values |
|---|---|
| profile | `funny`, `irl`, `gaming`, `gta6`: tells the AI what kind of moments go viral for this streamer |
| layout | `full` (whole screen on blurred background), `center` (crop the middle; good for IRL), `facecam` (facecam on top, gameplay below; needs a preset) |
| preset | a streamer name from `presets/streamers.json`, which stores their profile, layout and facecam position |

### Adding a streamer preset (for the facecam layout)
Take a screenshot of their stream. Measure where the facecam box is as fractions of the screen:
`x,y,width,height`. A cam in the bottom-right quarter is roughly `0.75,0.70,0.25,0.30`. Add:
```json
"streamername": { "profile": "gta6", "layout": "facecam", "facecam": "0.75,0.70,0.25,0.30" }
```

## Running on your own PC (optional)
Needs Python 3.12, ffmpeg and ~2 GB free space:
```
pip install -r requirements.txt
python -m clipper https://www.twitch.tv/videos/1234567890 --profile gta6 --layout full
```
