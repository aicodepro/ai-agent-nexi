import speech_recognition as sr
import random

def speak(text):
    try:
        from engine.command import speak as authoritative_speak
        authoritative_speak(str(text))
    except Exception as e:
        print(f"Error in game speak function: {e}")

def takeCommand():
    r = sr.Recognizer()
    with sr.Microphone() as source:
        speak("Listening.....")
        r.pause_threshold = 1
        r.energy_threshold = 300
        audio = r.listen(source,0,4)

    try:
        speak("Recognizing..")
        query = r.recognize_google(audio , language= 'en-in')
        speak(f"You Said : {query}\n")
    except Exception as e:
        speak("Say that again")
        return "None"
    return query

def game_play():
    speak("Lets Play ROCK PAPER SCISSORS !!")
    i = 0
    Me_score = 0
    Com_score = 0
    while(i<5):
        choose = ("rock","paper","scissors") #Tuple
        com_choose = random.choice(choose)
        query = takeCommand().lower()
        if (query == "rock"):
            if (com_choose == "rock"):
                speak("ROCK")
                speak(f"Score:- ME :- {Me_score} : COM :- {Com_score}")
            elif (com_choose == "paper"):
                speak("paper")
                Com_score += 1
                speak(f"Score:- ME :- {Me_score} : COM :- {Com_score}")
            else:
                speak("Scissors")
                Me_score += 1
                speak(f"Score:- ME :- {Me_score} : COM :- {Com_score}")

        elif (query == "paper" ):
            if (com_choose == "rock"):
                speak("ROCK")
                Me_score += 1
                speak(f"Score:- ME :- {Me_score+1} : COM :- {Com_score}")

            elif (com_choose == "paper"):
                speak("paper")
                speak(f"Score:- ME :- {Me_score} : COM :- {Com_score}")
            else:
                speak("Scissors")
                Com_score += 1
                speak(f"Score:- ME :- {Me_score} : COM :- {Com_score}")

        elif (query == "scissors" or query == "scissor"):
            if (com_choose == "rock"):
                speak("ROCK")
                Com_score += 1
                speak(f"Score:- ME :- {Me_score} : COM :- {Com_score}")
            elif (com_choose == "paper"):
                speak("paper")
                Me_score += 1
                speak(f"Score:- ME :- {Me_score} : COM :- {Com_score}")
            else:
                speak("Scissors")
                speak(f"Score:- ME :- {Me_score} : COM :- {Com_score}")
        i += 1
    
    speak(f"FINAL SCORE :- ME :- {Me_score} : COM :- {Com_score}")
    

            

