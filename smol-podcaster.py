import argparse
import requests
from dotenv import load_dotenv
import sys
import os
import re
from datetime import datetime
import json

import replicate
import openai
from anthropic import Anthropic, HUMAN_PROMPT, AI_PROMPT
from upload import upload_file, get_public_url

from upload import upload_file, get_public_url

load_dotenv()

openai.api_key = os.environ.get("OPENAI_API_KEY")
anthropic = Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

def transcribe_audio(file_url, transcription_nudge, num_speakers, episode_name):
    output = replicate.run(
        "thomasmol/whisper-diarization:7e5dafea13d80265ea436e51a310ae5103b9f16e2039f54de4eede3060a61617",
        input={
            "file_url": file_url,
            "num_speakers": num_speakers,
            "prompt": transcription_nudge
        }
    )
    
    with open(f"./podcasts-raw-transcripts/{episode_name}.json", "w") as f:
        json.dump(output, f)

    print('Raw transcript saved to ./podcasts-raw-transcripts/{episode_name}.md')

    return output['segments']

def process_transcript(transcript, episode_name):
    """
    {
        "end": "3251",
        "text": " This was great.  Yeah, this has been really fun.",
        "start": "3249",
        "speaker": "SPEAKER 1"
    }
        
    The transcript argument of this function is an array of these. 
    """
    
    transcript_strings = []
    
    for entry in transcript:
        speaker = entry["speaker"]
        text = entry["text"]

        # Divide "end" value by 60 and convert to hours, minutes and seconds
        seconds = int(entry["end"])
        minutes, seconds = divmod(seconds, 60)
        hours, minutes = divmod(minutes, 60)

        timestamp = "[{:02d}:{:02d}:{:02d}]".format(hours, minutes, seconds)

        transcript_strings.append(f"**{speaker}**: {text} {timestamp}")
        
    clean_transcript = "\n\n".join(transcript_strings)
    
    with open(f"./podcasts-clean-transcripts/{episode_name}.md", "w") as f:    
        f.write(clean_transcript)

    print('Transcript saved to ./podcasts-clean-transcripts/{episode_name}.md')
        
    return clean_transcript
    
 
def create_chapters(transcript):
    anthropic = Anthropic(
        api_key=os.environ.get("ANTHROPIC_API_KEY"),
    )
        
    chapters = anthropic.completions.create(
        model="claude-2",
        max_tokens_to_sample=3000,
        prompt=f"{HUMAN_PROMPT} Here's a podcast transcript with timestamps. Generate a list of all major topics covered in the podcast, and the timestamp at which it's mentioned in the podcast. Use this format: - [00:00:00] Topic name. Here's the transcript: \n\n {transcript} {AI_PROMPT}",
    )
    
    print(chapters.completion)
    
    return chapters.completion

def create_show_notes(transcript):
    anthropic = Anthropic(
        api_key=os.environ.get("ANTHROPIC_API_KEY"),
    )
        
    chapters = anthropic.completions.create(
        model="claude-2",
        max_tokens_to_sample=3000,
        prompt=f"{HUMAN_PROMPT} I'll give you a podcast transcript; help me create a list of every company, person, project, or any other named entitiy that you find in it. Here's the transcript: \n\n {transcript} {AI_PROMPT}",
    )
    
    print(chapters.completion)
    
    return chapters.completion

def title_suggestions(titles, transcript):
    title_list = "\n".join([f"{i+1}. \"{item}\"" for i, item in enumerate(titles)])
    prompt = f"""
    These are some titles of previous podcast episodes we've published:

    {title_list}

    Here's a transcript of the podcast episode; suggest 8 title options for it:
    
    {transcript}
    """
    
    try:
        result = openai.ChatCompletion.create(
            model="gpt-3.5-turbo-16k", 
            temperature=0.7,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )
        gpt_suggestions = result.choices[0].message.content
    except openai.error.InvalidRequestError as e:
        print(f"An error occurred: {e}")
        gpt_suggestions = "Out of context for GPT"
        
    claude_suggestions = anthropic.completions.create(
        model="claude-2",
        max_tokens_to_sample=3000,
        temperature=0.7,
        prompt=f"{HUMAN_PROMPT} {prompt} {AI_PROMPT}",
    )

    claude_suggestions = claude_suggestions.completion

    suggestions = f"GPT-3.5 16k title suggestions:\n\n{gpt_suggestions}\n\nClaude's title suggestions:\n{claude_suggestions}\n"

    print(suggestions)

    return suggestions
    
def tweet_suggestions(transcript):
    prompt = f"""
    Here's a transcript of our latest podcast episode; suggest 8 tweets to share it on social medias.
    It should include a few bullet points of the most interesting topics. Our audience is technical.
    Use a writing style between Hemingway's and Flash Fiction. 
    
    {transcript}
    """
    
    try:
        result = openai.ChatCompletion.create(
            model="gpt-3.5-turbo-16k", 
            temperature=0.7,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )
        gpt_suggestions = result.choices[0].message.content
    except openai.error.InvalidRequestError as e:
        print(f"An error occurred: {e}")
        gpt_suggestions = "Out of context for GPT"

    anthropic = Anthropic(
        api_key=os.environ.get("ANTHROPIC_API_KEY"),
    )
        
    claude_suggestions = anthropic.completions.create(
        model="claude-2",
        max_tokens_to_sample=3000,
        temperature=0.7,
        prompt=f"{HUMAN_PROMPT} {prompt} {AI_PROMPT}",
    )

    claude_suggestions = claude_suggestions.completion

    suggestions = f"GPT-3.5 16k tweet suggestions:\n{gpt_suggestions}\n\nClaude's tweet suggestions:\n{claude_suggestions}\n"
    
    print(suggestions)
    
    return suggestions

def is_valid_filename(filename):
    return bool(re.match("^[a-zA-Z0-9-_]+$", filename))

def is_url(path):
    url_regex = re.compile(r'http[s]?://.+')
    return bool(url_regex.match(path))

def main():
    parser = argparse.ArgumentParser(description="Transcribe the podcast audio from an URL like tmpfiles.")
    parser.add_argument("path", help="The path of the podcast to be processed.")

    args = parser.parse_args()

    path = args.path
    filename = os.path.split(path)[1]
    name = os.path.splitext(filename)[0]
    
    raw_transcript_path = f"./podcasts-raw-transcripts/{name}.json"
    clean_transcript_path = f"./podcasts-clean-transcripts/{name}.md"
    results_file_path = f"./podcasts-results/{name}.md"

    show_description = "A technical podcast about artificial intelligence and machine learning"
    episode_description = "…"
    speaker_count = 3
    titles =  [
        "This Month in React – August 2023",
        "This Month in React – July 2023",
        "Office Hours – States of Burnout with Jenny Truong",
        "This Month in React – June 2023",
        "This Month in React – May 2023",
        "Office Hours – Professional Communication with Elizabeth Woolf",
        "This Month in React – April 2023",
        "Community Spotlight – React Miami with Michelle Bakels",
        "This Month In React – March 2023",
        "Office Hours – Rewrites, with Sunil Pai and Mark Erikson",
        "Office Hours – Becoming a leader with Ankita Kulkarni",
    ]
    notable_names = [
        "…"
    ]
    print(f"Running smol-podcaster on {path}")
    url = ''
    if is_url(path):
        url = path
    else:
        upload_file(path, f"podcasts/{name}")
        url = get_public_url(f"podcasts/{name}")

    # These are probably not the most elegant solutions, but they 
    # help with saving time since transcriptions are the same but we
    # might want to tweak the other prompts for better results.
    
    if not os.path.exists(raw_transcript_path):
        print('Transcribing audio...', file=sys.stderr)
        transcript = transcribe_audio(
            file_url=url,
            transcription_nudge=f"{show_description}\n\nThis episode: {episode_description}\n\nHere are some notable names that are likely to be used in the transcript:\n{notable_names}\n\n",
            num_speakers=speaker_count,
            episode_name=name
        )
        print('Transcribing audio... done')
    else:
        print('Loading existing transcript from file')
        file = open(raw_transcript_path, "r").read()
        transcript = json.loads(file)['segments']
        
    if not os.path.exists(clean_transcript_path):
        print('Cleaning transcript...', file=sys.stderr)
        transcript = process_transcript(transcript, name)
        print('Cleaning transcript... done')
    else:
        print('Loading clean transcript from file')
        transcript = open(clean_transcript_path, "r").read()
    
    print('Creating chapters...', file=sys.stderr)
    chapters = create_chapters(transcript)
    print('Creating show notes...', file=sys.stderr)
    show_notes = create_show_notes(transcript)
    print('Creating recommended titles...', file=sys.stderr)
    title_suggestions_str = title_suggestions(titles, transcript)
    print('Creating recommended titles...', file=sys.stderr)
    tweet_suggestions_str = tweet_suggestions(transcript)

    with open(results_file_path, "w") as f:
        f.write("Chapters:\n")
        f.write(chapters)
        f.write("\n\n")
        f.write("Show Notes:\n")
        f.write(show_notes)
        f.write("\n\n")
        f.write("Title Suggestions:\n")
        f.write(title_suggestions_str)
        f.write("\n\n")
        f.write("Tweet Suggestions:\n")
        f.write(tweet_suggestions_str)
        f.write("\n")
    
    print(f"Results written to {results_file_path}")
    

if __name__ == "__main__":
    main()
