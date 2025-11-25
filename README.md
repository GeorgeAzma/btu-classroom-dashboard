![BTU Dashboard](btu.png)

# BTU Classroom Dashboard

Personal dashboard for BTU Classroom. Shows courses, grades, materials.

## Setup
1. Clone repo
2. Go to http://classroom.btu.edu.ge
3. Sign in and press F12
4. Go to network tab and refresh page
5. Press `courses`
6. inside `Headers` tab, find `Cookie` field
7. select and copy whole `Cookie` value, it should looks like this:
```
_gcl_au=1.1.1745258531.1758911965; argus_session=svu01itqrc43uu5pvgj89s2cr; sbjs_migrations=1418474375911%3D1; sbjs_first_add=ad%3D2025-10-26%2018%3A02%3A16%7C%7C%7Cep%3Dhttps%3A%2F%2Fbtu.edu.ge%2F%7C%7C%7Crf%3D%28none%29; sbjs_first=typ%3Dtypein%7C%7C%7Csrc%3D%28direct%29%7C%7C%7Cmdm%3D%28none%29%7C%7C%7Ccmp%3D%28none%29%7C%7C%7Ccnt%3D%28none%29%7C%7C%7Ctrm%3D%28none%29%7C%7C%7Cid%3D%28none%29%7C%7C%7Cplt%3D%28none%29%7C%7C%7Cfmt%3D%28none%29%7C%7C%7Ctct%3D%28none%29; sbjs_current_add=fd%3D2025-11-11%2022%3A59%3A44%7C%7C%7Cep%3Dhttps%3A%2F%2Fbtu.edu.ge%2F%3Futm_source%3Dchatgpt.com%7C%7C%7Crf%3Dhttps%3A%2F%2Fchatgpt.com%2F; sbjs_current=typ%3Dutm%7C%7C%7Csrc%3Dchatgpt.com%7C%7C%7Cmdm%3D%28none%29%7C%7C%7Ccmp%3D%28none%29%7C%7C%7Ccnt%3D%28none%29%7C%7C%7Ctrm%3D%28none%29%7C%7C%7Cid%3D%28none%29%7C%7C%7Cplt%3D%28none%29%7C%7C%7Cfmt%3D%28none%29%7C%7C%7Ctct%3D%28none%29; _gid=GA1.3.80463346.1764087635; sbjs_udata=vst%2D10%7C%7C%7Cuip%3D%28none%29%7C%7C%7Cuag%3DMozilla%2F5.0%20%28Windows%20NT%2010.0%3B%20Win64%3B%20x64%29%20AppleWebKit%2F537.36%20%28KHTML%2C%20like%20Gecko%29%20Chrome%2F142.0.0.0%20Safari%2F537.36; _ga_Z3J6WZG5WL=GS2.1.s1764104115$o17$g0$t17641041515$j60$l0$h0; _ga=GA1.1.1495400961.1758911963; _ga_GB7ZZ5PPHE=GS2.1.s1764104115$o17$g0$t1764104115$j60$l0$h0; cf_clearance=0cW7RsDbi6GPksm44zWYmou13jOWHQ3Va.QM6.zIVP8-1764112602-1.2.1.1-KqElI8_RiJ51F2Cb28945c0OZxRX2fUvYwHacIl0HQyXAneN3MA2VAgysSdjPfZXRKK2fdGU4eo56E6uVbZdm.yPU8uVEVd0LFVy2ROFSUr0C1mlzi1oMlkVe4iqweq6PuT2E3T8plNAOfmssfo6sALdk2WgaKM3oBKpPZV9yXVsYqo0VwxxQizGdPtqcGTNFD4kR7mxpzoPXcB2vTW2tleuBDKqvgtMbAlC0e81Wz8
```
8. Create `.env` file inside repo folder and paste your cookie:
```
cookie=your_btu_classroom_cookie
```
9. open terminal inside repo folder and run:
``` bash
# make sure python is installed
python3 -m venv .venv
pip install -r requirements.txt
python3 main.py
```
10. Go to http://localhost:1111
11. Enjoy nice UI and not having to click 100 times to check your grades

### Notes
- Grades are updated every rerun
- Stop the script by pressing `Ctrl + C` inside terminal
- If you have a problem open Issue on GitHub, or comment on the post