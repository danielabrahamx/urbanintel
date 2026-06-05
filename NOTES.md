# Urban Intelligence Agent research notes

## TfL JamCam API

Endpoint inspected:

```text
GET https://api.tfl.gov.uk/Place/Type/JamCam
```

Anonymous `curl` access returned HTTP 200 with JSON. A plain Python
`urllib.request.urlopen()` call returned HTTP 403, so the MVP uses `requests`,
matching the intended implementation.

### Camera object structure

The response is a JSON array of camera objects. In the inspected response there
were 882 camera objects.

Each object has this top-level shape:

```json
{
  "$type": "Tfl.Api.Presentation.Entities.Place, Tfl.Api.Presentation.Entities",
  "id": "JamCams_00002.00865",
  "url": "/Place/JamCams_00002.00865",
  "commonName": "A406 Billet Upass E",
  "placeType": "JamCam",
  "additionalProperties": [],
  "children": [],
  "childrenUrls": [],
  "lat": 51.60067,
  "lon": -0.01594
}
```

### `additionalProperties`

Observed keys:

| key | category | sourceSystemKey | meaning |
| --- | --- | --- | --- |
| `available` | `payload` | `JamCams` | String boolean such as `"true"` |
| `imageUrl` | `payload` | `JamCams` | Direct HTTPS JPG URL |
| `videoUrl` | `payload` | `JamCams` | Direct HTTPS MP4 URL |
| `view` | `cameraView` | `JamCams` | Human-readable camera direction/view |

Example:

```json
{
  "$type": "Tfl.Api.Presentation.Entities.AdditionalProperties, Tfl.Api.Presentation.Entities",
  "category": "payload",
  "key": "videoUrl",
  "sourceSystemKey": "JamCams",
  "value": "https://s3-eu-west-1.amazonaws.com/jamcams.tfl.gov.uk/00002.00865.mp4",
  "modified": "2026-05-26T17:34:51.13Z"
}
```

### Video vs image availability

In the inspected response:

- Cameras with `imageUrl`: 882
- Cameras with `videoUrl`: 882
- Cameras with both: 882
- Cameras with only `imageUrl`: 0

The code still checks for a missing `videoUrl` because TfL availability can
change by camera and over time.

### Central London candidates

Filter used:

```text
51.48 < lat < 51.54
-0.15 < lon < -0.05
```

This returned 173 central London cameras with `videoUrl`.

Useful busy-junction candidates included:

| camera_id | name | lat | lon | notes |
| --- | --- | ---: | ---: | --- |
| `JamCams_00001.07350` | City Road/Old Street | 51.5262 | -0.08771 | Old Street / City Road junction; selected for MVP |
| `JamCams_00001.01260` | Old Street/Gt Eastern St | 51.5265 | -0.08414 | Old Street / Great Eastern Street |
| `JamCams_00001.04244` | Westminster Bridge Rd/Waterloo Rd | 51.4986 | -0.10545 | Waterloo station approach |
| `JamCams_00001.07450` | Piccadilly Circus | 51.5096 | -0.13484 | Busy central junction |
| `JamCams_00001.04276` | Nine Elms Ln/Wandsworth Rd | 51.4848 | -0.12858 | Vauxhall Cross view |

`JamCams_00001.04256` is labelled Vauxhall Cross but the downloaded MP4 was only
1 second in the inspected sample, so it was not selected.

### Selected camera

Selected `TARGET_CAMERA_ID`:

```python
TARGET_CAMERA_ID = "JamCams_00001.07350"
```

Camera:

```text
City Road/Old Street
lat=51.5262
lon=-0.08771
view="Old Street west of City Road"
videoUrl=https://s3-eu-west-1.amazonaws.com/jamcams.tfl.gov.uk/00001.07350.mp4
```

### Downloaded video details

The selected `videoUrl` is a direct Amazon S3 HTTPS MP4 link. It did not require
TfL credentials or signed auth when tested.

HTTP response:

```text
HTTP 200
Content-Type: video/mp4
```

`ffprobe` output for `00001.07350.mp4`:

```text
codec=h264
resolution=352x288
frame_rate=25 fps
duration=10.400000 seconds
size=137912 bytes
container=mov,mp4,m4a,3gp,3g2,mj2
```

Other verified 10-second-ish MP4s:

- `00001.04244.mp4`: 11.24s, H.264, 352x288, 25fps
- `00001.07450.mp4`: 10.76s, H.264, 352x288, 25fps
- `00001.01260.mp4`: 10.32s, H.264, 352x288, 25fps
- `00001.04276.mp4`: 10.36s, H.264, 352x288, 25fps

## Gemini Files API for video

The MVP uses the `google-generativeai` Python SDK:

```python
import google.generativeai as genai
```

Confirmed implementation details:

- Configure with `genai.configure(api_key=os.environ["GEMINI_API_KEY"])`.
- Upload local MP4 clips with
  `genai.upload_file(video_path, mime_type="video/mp4")`.
- Poll processing state before model inference:
  `uploaded_file = genai.get_file(uploaded_file.name)` until
  `uploaded_file.state.name == "ACTIVE"`.
- Treat any non-`ACTIVE` terminal state as a failure.
- Pass the uploaded file object directly to the model alongside the prompt:
  `model.generate_content([uploaded_file, prompt], ...)`.
- Use `gemini-2.0-flash` for the MVP.
- Request JSON output with
  `generation_config={"response_mime_type": "application/json"}`.
- Delete the uploaded file after analysis with
  `genai.delete_file(uploaded_file.name)`.

## Prior art

- Conntour: natural-language search and alerts across existing security camera
  feeds; validates querying camera footage with text prompts.
- Lexius: uses existing CCTV to detect and document incidents without new
  hardware; validates the "software layer over existing cameras" approach.
- arXiv 2402.02205, "GPT-4V as Traffic Assistant": studies VLMs on complex
  traffic-event videos and finds strong ability on representative incidents,
  while noting limitations in more complex scenes.
