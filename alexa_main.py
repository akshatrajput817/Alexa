import traceback
import speech_recognition as sr
import pyttsx3
import webbrowser
import pyautogui
import json
import subprocess
import time
import random
import os
import pyjokes
from datetime import datetime
import difflib
from orb import bridge, run_app   # <-- orb connection



#Websites
websites = {
    # Search Engines
    "google": "https://www.google.com",
    "bing": "https://www.bing.com",

    # AI Websites
    "chat": "https://chatgpt.com",
    "gemini": "https://gemini.google.com",
    "claude": "https://claude.ai",
    "deepseek": "https://chat.deepseek.com",
    "perplexity": "https://www.perplexity.ai",
    "copilot": "https://copilot.microsoft.com",
    "grok": "https://grok.com",
    "netlify": "https://www.netlify.com/",

    # AI Coding Tools
    "claude code": "https://docs.anthropic.com/en/docs/claude-code/overview",
    "github copilot": "https://github.com/features/copilot",
    "replit": "https://replit.com",
    "cursor": "https://cursor.com",

    # Social Media & Messaging
    "telegram": "https://web.telegram.org",
    "discord": "https://discord.com/app",
    "instagram": "https://www.instagram.com",
    "facebook": "https://www.facebook.com",
    "messenger": "https://www.messenger.com",
    "twitter": "https://x.com",
    "reddit": "https://www.reddit.com",
    "linkedin": "https://www.linkedin.com",
    "snapchat": "https://web.snapchat.com",

    # Video & Entertainment
    "netflix": "https://www.netflix.com",
    "spotify": "https://open.spotify.com",
    "twitch": "https://www.twitch.tv",

    # Coding & Learning
    "github": "https://github.com",
    "stackoverflow": "https://stackoverflow.com",
    "w3schools": "https://www.w3schools.com",
    "geeksforgeeks": "https://www.geeksforgeeks.org",
    "programiz": "https://www.programiz.com",
    "python": "https://www.python.org",

    # Google Services
    "gmail": "https://mail.google.com",
    "google drive": "https://drive.google.com",
    "google maps": "https://maps.google.com",
    "google translate": "https://translate.google.com",
    "google meet": "https://meet.google.com",

    # Shopping
    "amazon": "https://www.amazon.in",
    "flipkart": "https://www.flipkart.com",

    # Other Useful Websites
    "canva": "https://www.canva.com",
    "wikipedia": "https://www.wikipedia.org",
    "irctc": "https://www.irctc.co.in",
    "speedtest": "https://www.speedtest.net"
}

website_name = ["google", "bing", "chat", "gemini", "claude", "deepseek", "perplexity", "copilot", "grok", "claude code", "github copilot", "replit", "cursor", "telegram", "discord", "instagram", "facebook", "messenger", "twitter", "reddit", "linkedin", "snapchat","netflix", "spotify", "twitch", "github", "stackoverflow", "w3schools", "geeksforgeeks", "programiz", "python", "gmail", "google drive", "google maps", "google translate", "google meet", "amazon", "flipkart", "canva", "wikipedia", "irctc", "speedtest","netlify"]

#apps--------------------------------------------------------------------------

apps = {
    "notepad": "notepad.exe",
    "calculator": "calc.exe",
    "paint": "mspaint.exe",
    "task": "taskmgr.exe",
    "file explorer": "explorer.exe",
    "command prompt": "cmd.exe",
    "powershell": "powershell.exe",
    "control panel": "control.exe",
    "setting": "ms-settings:",
    "settings": "ms-settings:",
    "registry editor": "regedit.exe",
    "services": "services.msc",
    "device manager": "devmgmt.msc",
    "disk management": "diskmgmt.msc",
    "event viewer": "eventvwr.msc",
    "system configuration": "msconfig.exe",
    "character map": "charmap.exe",
    "on screen keyboard": "osk.exe",
    "magnifier": "magnify.exe",
    "remote desktop": "mstsc.exe",
    "windows media player": "wmplayer.exe",
    "snipping tool": "SnippingTool.exe",
    "sound recorder": "SoundRecorder.exe",
    "photos": "ms-photos:",
    "camera": "microsoft.windows.camera:",
    "browser": "msedge.exe",
    "visual studio": "code.exe"
}

application_name = ["notepad", "calculator", "paint", "snipping tool", "task", "file explorer", "command prompt", "powershell", "control panel", "setting", "registry editor", "services", "device manager", "disk management", "event viewer", "system configuration", "character map", "on screen keyboard", "magnifier", "remote desktop", "windows media player", "sound recorder", "photos", "camera","visual studio","browser"]
#Common_taks----------------------------------------------------
talk = {
    # Thanks & Polite Commands
    "ok alexa thanks": "My pleasure, sir.",
    "ok alexa thank you": "My pleasure, sir.",
    "ok alexa good job": "Thank you, sir!",
    "ok alexa well done": "I appreciate that, sir.",

    # Questions About Alexa
    "ok alexa who are you": "I am Alexa, your personal voice assistant.",
    "ok alexa introduce yourself": "I am Alexa, your personal voice assistant. I can automate your work and save your valuable time. I was created by Akshat Rajput.",
    "ok alexa what can you do": "I can automate your work and save your valuable time, sir.",
    "ok alexa are you intelligent": "I am designed to assist you, sir.",
    "ok alexa what's your name": "My name is Alexa.",
    "ok alexa who created you": "I was created by Akshat Rajput.",
    "ok alexa do you like me": "I am always ready to assist you, sir.",
    "ok alexa can you listen me": "Yes sir, I can listen you.",

    # Exit Commands
    "ok alexa bye": "bye, sir! Have a great day.",
    "ok alexa see you later": "See you later, sir.",
}
voice_commands = [
    # Thanks & Polite Commands
    "ok alexa good job",
    "ok alexa well done",

    # Questions About Alexa
    "ok alexa who are you",
    "ok alexa introduce yourself",
    "ok alexa what can you do",
    "ok alexa are you intelligent",
    "ok alexa what's your name",
    "ok alexa who created you",
    "ok alexa do you like me",

    "ok alexa can you listen me",

    # Exit Commands
    "ok alexa see you later",
    
]
contacts_name = [
    "ignore this", "itzz me @rashi❤️", "kanchan mam", "nishi3", "real sristtyy",
    "aryan", "twinkle 🤩", "neetu mamiji ji", "tanvi naveen", "jyoti bhabhi",
    "dhanu manu", "varsha kartik", "atharv new", "~preeti", "sandhya",
    "atul mama ji 2", "shiv jiju2", "swati chachi khera", "archana ki bhabhi", "bhawna mosii",
    "sudha nani ji", "real atharv", "aditi", "soamya", "nisha",
    "aishwarya sir", "gilmaan", "nanoo di", "nilakshi mausi ji", "vikku bhaiya",
    "papa ji", "drive rajput", "rekha taiji", "karuna bhabhi", "khushboo rashi friend",
    "neeraj bhaiya", "aditya chauchansahab jiiiii", "atul mama ji", "mange bhiya", "parul mausi",
    "nilima", "rajat bijnore bijnore", "saakshi 2", "pulkit sir", "harsh",
    "archna balmiki", "neelam", "meena", "mamta friend", "sudha di",
    "puja bhabhi", "mohammad sabir", "ashad", "aaradhya"
]
contacts_nickname = {
    "ignore": "ignore this",
    "rashi": "itzz me @rashi❤️",
    "kanchan": "kanchan mam",
    "nishi": "nishi3",
    "sristtyy": "real sristtyy",
    "aryan": "aryan",
    "twinkle": "twinkle 🤩",
    "neetu": "neetu mamiji ji",
    "tanvi": "tanvi naveen",
    "jyoti": "jyoti bhabhi",
    "dhanu": "dhanu manu",
    "varsha": "varsha kartik",
    "preeti": "~preeti",
    "sandhya": "sandhya",
    "atul2": "atul mama ji 2",
    "shiv": "shiv jiju2",
    "swati": "swati chachi khera",
    "archana": "archana ki bhabhi",
    "bhawna": "bhawna mosii",
    "sudha nani": "sudha nani ji",
    "atharv": "real atharv",
    "aditi": "aditi",
    "soamya": "soamya",
    "nisha": "nisha",
    "aishwarya": "aishwarya sir",
    "gilmaan": "gilmaan",
    "nanoo": "nanoo di",
    "nilakshi": "nilakshi mausi ji",
    "vikku": "vikku bhaiya",
    "papa": "papa ji",
    "drive": "drive rajput",
    "rekha": "rekha taiji",
    "karuna": "karuna bhabhi",
    "khushboo": "khushboo rashi friend",
    "neeraj": "neeraj bhaiya",
    "aditya": "aditya chauchansahab jiiiii",
    "atul": "atul mama ji",
    "mange": "mange bhiya",
    "parul": "parul mausi",
    "nilima": "nilima",
    "rajat": "rajat bijnore bijnore",
    "saakshi": "saakshi 2",
    "pulkit": "pulkit sir",
    "harsh": "harsh",
    "archna": "archna balmiki",
    "neelam": "neelam",
    "meena": "meena",
    "mamta": "mamta friend",
    "sudha": "sudha di",
    "puja": "puja bhabhi",
    "mohammad": "mohammad sabir",
    "ashad": "ashad",
    "aaradhya": "aaradhya"
}
recognizer = sr.Recognizer()
recognizer.dynamic_energy_threshold = False  
recognizer.energy_threshold = 300             
recognizer.pause_threshold = 1.2    
recognizer.operation_timeout = 8
def speak(text):
    bridge.heartbeat = time.time() 
    bridge.message.emit("ALEXA", str(text))          # <-- orb: chat me message
    bridge.state_changed.emit("SPEAKING")            # <-- orb: speaking
    engine = pyttsx3.init()
    voices = engine.getProperty("voices")
    engine.setProperty("voice", voices[1].id)

    engine.setProperty("rate", 170)
    engine.setProperty("volume", 1.0)
    engine.say(text)
    engine.runAndWait()
    engine.stop()
    bridge.state_changed.emit("IDLE")    
    bridge.heartbeat = time.time()    # <-- orb: idle
print("Initalizing Alexa...")
speak("Intializing Alexa")
def nova_process(cmd):
    cmd = cmd.lower().strip()
    if "open youtube" in cmd:
        if "search" in cmd:
            index = cmd.find("search")
            text = cmd[index+ len("search"):].strip()
            text_final = text.replace(" ","+")
            url = (f"https://www.youtube.com/results?search_query={text_final}")
            webbrowser.open(url)
            speak("Sir, here are your results")
            return "complete"
        elif "play" in cmd:
            index = cmd.find("play")
            text = cmd[index + len("play"):].strip()
            text_final = text.replace(" ","+")
            url = (f"https://www.youtube.com/results?search_query={text_final}")
            webbrowser.open(url)
            time.sleep(6)
            pyautogui.click(500, 400)
            time.sleep(2)
            pyautogui.press("f")
            speak("Sir, here are your YouTube search results")
            return "complete"

        else:
            webbrowser.open("https://www.youtube.com")
            speak("Sir, I have opened Youtube.")
            return "complete"
    if "open whatsapp" in cmd or "send" in cmd: 
        if "send message" in cmd or "send a message" in cmd or "message" in cmd  or "send msg" in cmd or "send a msg" in cmd or "send" in cmd:
            for nickname in sorted(contacts_nickname, key=len, reverse=True):
                if nickname in cmd:
                   user = contacts_nickname[nickname]
                   print(f"User : {user}")
                   break 
            index_whtsp = cmd.lower().find(nickname)
            msg = cmd[index_whtsp + len(nickname):].strip()
            if "that" in cmd or "ki" in cmd:
                if "that" in cmd:
                    message = msg.replace("that ","")
                elif "ki" in cmd:
                    message = msg.replace("ki ","")
            else:
                message = msg
            print(f"Message : {message}")
            webbrowser.open("https://web.whatsapp.com/")
            time.sleep(11)
            pyautogui.click(283, 199)
            time.sleep(1)
            pyautogui.write(user,interval=0.2)
            time.sleep(0.5)
            pyautogui.click(278, 355)
            time.sleep(1)
            pyautogui.write(message,interval=0.1)
            time.sleep(0.5)
            pyautogui.press("enter")
            speak("Sir, your message has been successfully sent to your friend.")
            return "complete"
        else:
            webbrowser.open("https://web.whatsapp.com/")
            speak("Sir I have succesfully opened Whatsapp")
    if "keep quiet" in cmd or "shut up" in cmd or "go to sleep" in cmd or "stop listen" in cmd or "take a rest" in cmd or "stop listening" in cmd:
        speak("Ok Sir going to sleep bye bye")
        return ("break")
    if "random" in cmd or "song" in cmd:
        song_path = r"C:\Users\rashi rajput\Desktop\favourite"
        songs = []
        for song in os.listdir(song_path):
            songs.append(song)
        if "random song" in cmd :
            random_song = random.choice(songs)
            speak(f"Okay sir! I've selected a random song for you. {random_song}")
            os.startfile(f"""{song_path}\\{random_song}""")
        elif "song" in cmd or "music" in cmd:
            index_song = cmd.find("song")
            song_search = cmd[index_song + len("song"):].strip()
            songs_withmp3 = os.listdir(song_path)
            songs_withoutmp3 = []
            for song1 in songs_withmp3:
                songs_withoutmp3.append(song1.lower().replace(".mp3",""))
            match = difflib.get_close_matches(song_search, songs_withoutmp3, n=1, cutoff=0.3)
            if match:
                index_song1 = songs_withoutmp3.index(match[0])
                selected_song = songs_withmp3[index_song1]
                speak(f"Okay sir! Playing {selected_song} for you.")
                os.startfile(fr"{song_path}\\{selected_song}")
                return "complete"
            if song_search == "":
                random_song = random.choice(songs)
                speak(f"Okay sir! I've selected a random song for you. {random_song}")
                os.startfile(f"""{song_path}\\{random_song}""")
                return "complete"
        else:
            return "incomplete"
    if "bhajan" in cmd:
        webbrowser.open("https://www.youtube.com/watch?v=zrBhj2hyi3k&list=RDzrBhj2hyi3k&start_radio=1")
        speak("Sir Bhajan Is Now Playing")
        return "complete"
    if "stop" in cmd or "pause" in cmd or "play" in cmd:
        if "video" in cmd:
            pyautogui.press("playpause")
            speak("Sir, the video has been paused successfully.")
            return "complete"
        elif "music" in cmd:
            pyautogui.press("playpause")
            speak("Sir, the music has been paused successfully.")
            return "complete"
    if "tab" in cmd:
        if "reopen" in cmd or "reopened" in cmd:
            pyautogui.hotkey("ctrl", "shift", "t")
            return "complete"
        elif "open" in cmd or "opened" in cmd:
            pyautogui.hotkey("ctrl","t")
            return "complete"
        elif "close" in cmd or "closed" in cmd:
            pyautogui.hotkey("ctrl","w")
            return "complete"
    if "scroll" in cmd:
        if "up" in cmd:
            speak("Sure Sir I will scroll up")
            for i in range(20):
                pyautogui.scroll(50)
            return "complete"
        if "down" in cmd:
            speak("sure sir i will scroll down")
            for i in range(20):
               pyautogui.scroll(-50)
            return "complete"
    for voice in voice_commands:
        if voice in cmd:
            speak(talk[voice])
            return "complete"
    for web_name in sorted(website_name,key = len,reverse=True):
        if (f"open {web_name}") in cmd:
            try:
                webbrowser.open(websites[web_name])
                speak(f"Sir, I have opened {web_name}.")
                return "complete"
                
            except Exception as e:
                speak(f"Sorry sir i can't open {web_name} ")
                print(e)
                return "incomplete"
            
            
    for app_name in sorted(application_name,key=len,reverse=True):
        if (f"open {app_name}" in cmd):
            try:
                os.startfile(apps[app_name])  
                speak(f"Sir, I have opened {app_name}.")
                return "complete"
        
            except:
                speak(f"Sorry sir i can't find {app_name} ")
                return "incomplete"
        if (f"close {app_name}"in cmd):
            subprocess.run(
            ["taskkill", "/im",app_name, "/f"],
            shell=True,creationflags=subprocess.CREATE_NO_WINDOW
)
    if "time" in cmd or "current date" in cmd or "current day" in cmd:
        if "the time" in cmd or "what time" in cmd or "current time" in cmd:
            current_time = datetime.now().strftime("%I:%M %p")
            speak(f"Sir current time is : {current_time}")
            return "complete"
        elif "current date" in cmd:
            today = datetime.now().strftime("%d %B %Y")
            speak(f"Sir, today's date is {today}")
            return "complete"
        elif "current day" in cmd:
            today = datetime.now().strftime("%A")
            speak(f"Sir, today is {today}")
            return "complete"
    if "shutdown" in cmd or "turn off" in cmd or "restart" in cmd or "sleep computer" in cmd or "sleep pc" in cmd:
        if "sleep computer" in cmd or "sleep pc" in cmd:
            speak("Going in Sleep Mode")
            os.system("rundll32.exe powrprof.dll,SetSuspendState 0,1,0")
            return "complete"
        if "turn off" in cmd or "shutdown" in cmd:
            if "cancel" in cmd:
                os.system("shutdown /a")
                speak("sir Shutdown cancelled! Your PC is safe")
                return "complete"
            else: 
                speak("ok sir Your PC is scheduled to shut down in 1 minute")
                os.system("shutdown /s /t 60")
                speak("If you change your mind, simply say Cancel to stop the shutdown")
                while True:
                    shut = listen()
                    if "cancel" in shut.lower():
                        os.system("shutdown /a")
                        speak("sir Shutdown cancelled! Your PC is safe")
                        return "complete"
                
        if "restart" in cmd:
            speak("Your PC is scheduled to restart in 30 seconds")
            os.system("shutdown /r /t 30")
            speak("If you've changed your mind, just say Cancel to stop the restart.")
            rest = listen()
            if "cancel" in rest.lower():
                os.system("shutdown /a")
                speak("sir restart cancelled! Your PC is safe")
                return("complete")
    if "volume" in cmd:
        if "increases" in cmd or "increase" in cmd:
              pyautogui.press("volumeup",presses=8)
              speak("Sir volume is increased now")
              return "complete"
        if "decreases" in cmd or "decrease" in cmd:
            pyautogui.press("volumedown",presses=8)
            speak("Sir volume is decreased now")
            return "complete"
    if "take screenshot" == cmd or "can you please take a screenshot" in cmd or "screenshot" in cmd:
        screenshot = pyautogui.screenshot()
        screenshot.save(r"C:\Users\rashi rajput\Pictures\Screenshots\Screenshot.png")
        speak("Sir I have Succesfully take a screenshot ")
    if "desktop" in cmd or "minimise" in cmd or "minimize" in cmd:
        pyautogui.hotkey("win","d")
        speak("Succesfully Minimize The Window")
        return "complete"
    if "write" in cmd or "type" in cmd:
        if cmd.startswith("ok alexa") or cmd.startswith("alexa"):
            index = cmd.find("alexa")
            text = cmd[index + len("alexa"):]
            if text.startswith("write"):
                index_write = text.find("write")
                text_write = text[index_write + len("write"):]
                pyautogui.write(text_write,interval=0.1)
                speak("Sir, I have successfully typed the text.")
                return "complete"
            if text.startswith("type"):
                index_write = text.find("type")
                text_write = text[index_write + len("type"):]
                pyautogui.write(text_write,interval=0.1)
                speak("Sir, I have successfully typed the text.")
                return "complete"
        elif cmd.startswith("write"):
            index = cmd.find("write")
            text = cmd[index + len("write"):]
            pyautogui.write(text,interval=0.1)
            speak("Sir, I have successfully typed the text.")
            return "complete"
        if cmd.startswith("type "):
           index = cmd.find("type")
           text = cmd[index + len("type"):]
           pyautogui.write(text,interval=0.1)
           speak("Sir, I have successfully typed the text.")
           return "complete"      
    if cmd.startswith("search"):
        text = cmd.replace("search ","")
        url = f"https://www.google.com/search?q={text}"
        webbrowser.open(url)
        return "complete"
    if "good job" in cmd or "well done" in cmd or "nice" in cmd or "great" in cmd or "awesome" in cmd or "perfect" in cmd or "excellent" in cmd or "amazing" in cmd or "keep it up" in cmd:
        speak("Thank you, sir! I'm always happy to help.")
        return "complete"
    if "joke" in cmd.lower():
        joke = pyjokes.get_joke()
        speak("sir. Here's a joke for you.")
        speak(joke)
        return "complete"
def main():
    empty_count = 0
    while True:
        bridge.wake_event.clear()                  
        if bridge.restart_event.is_set():          
            bridge.restart_event.clear()
            print("[Alexa] Restart pressed -> going to sleep")
            speak("Restarting. Going to sleep mode.")
            break                                  # sleep loop mein wapas
        command = listen()
        print("Listen finished!")
        if not command:
            empty_count = empty_count+1
            if empty_count == 20:
                speak("No command received. Going to sleep mode.")
                break
            continue
        print("Alexa processing started!")
        cmd_work = nova_process(command)
        print("Alexa processing finished!")
        if cmd_work == "break":
            break
        if cmd_work == "complete":
            subprocess.run("cls",shell=True,creationflags=subprocess.CREATE_NO_WINDOW)
            bridge.clear_log.emit()
            

def listen(wake=False):
    bridge.heartbeat = time.time()
    stage = "Microphone initialization"
    bridge.stage = stage 
    print(stage)
    try:
        with sr.Microphone() as source1:
            print("Listening....")

            if not wake:
                bridge.state_changed.emit("LISTENING")

            stage = "Audio recording"
            bridge.stage = stage 
            print(stage)
            audio = recognizer.listen(
                source1,
                timeout=2,
                phrase_time_limit=5 if wake else 30
            )

        print("Reconizing....")
        stage = "Google speech recognition"
        bridge.stage = stage
        if stage == "STUCK":
            return "" 
        print(stage)
        word_normal = recognizer.recognize_google(audio)

        print(f"Recognise By Alexa : {word_normal}")

        if (not wake) or ("alexa" in word_normal.lower()):
            bridge.message.emit("YOU", word_normal)

        return word_normal.lower()

    except sr.WaitTimeoutError:
        return ""

    except sr.UnknownValueError:
        print("Sorry, voice samajh nahi aayi.")
        return ""

    except sr.RequestError as e:
        print(f"Google Speech Recognition error: {e}")
        return ""

    except Exception as e:
        print(f"Error during: {stage}")
        print(f"Unexpected error: {e}")
        traceback.print_exc()
        return ""

    finally:
        bridge.heartbeat = time.time()
        bridge.stage = "idle" 

        if not wake:
            bridge.state_changed.emit("IDLE")
          # <-- orb: idle                       
def login():
    speak("Speak Your Password")
    speak("Security Alert: 30 seconds shutdown timer started...")
    os.system("shutdown /s /t 30")
    while True:
        password = listen()
        if "hello" in password.lower():
                os.system("shutdown /a")
                speak("Login Succesfully")
                time.sleep(1)
                speak("Welcome, sir. Please say the magic word to unlock Alexa.")
                break
#if os.environ.get("ALEXA_SKIP_LOGIN") != "1":
    #login()   


def alexa_loop():
    while True:
        try:
            # NEW: Restart button (sleep mode mein)
            if bridge.restart_event.is_set():
                bridge.restart_event.clear()
                print("[Alexa] Restarted -> sleep mode")
                bridge.state_changed.emit("IDLE")
                continue

            # NEW: Wake Up button
            if bridge.wake_event.is_set():
                bridge.wake_event.clear()
                print("[Alexa] Wake Up button pressed")
                word = "alexa"
            else:
                word = listen(wake=True)

            if "alexa" in word.lower():
                speak("Hello sir, how can I help you?")
                main()
        except Exception as e:
            print("Loop error:", e)
            time.sleep(1)

run_app(alexa_loop)      # <-- orb window start + alexa background me