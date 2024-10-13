import os
import multiprocessing
import requests
import json
import time
import logging
import certifi
from pymongo import MongoClient
from pdfminer.high_level import extract_text
from collections import Counter
import math

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# MongoDB connection details
username = "myUser"
password = "myPassword"
cluster_url = "cluster0.15de1.mongodb.net"
connection_string = f"mongodb+srv://{username}:{password}@{cluster_url}/test?retryWrites=true&w=majority"

# Connect to MongoDB Atlas
try:
    client = MongoClient(connection_string)
    db = client['pdf_pipeline']
    collection = db['pdf_documents']
    logging.info("Connected to MongoDB Atlas successfully.")
except Exception as e:
    logging.error(f"Failed to connect to MongoDB Atlas: {e}")
    raise

# Dataset path
DATASET_PATH = r"D:\Downloads\Dataset Wasserstoff.json"

# Load dataset
def load_dataset(path):
    try:
        with open(path, 'r') as file:
            dataset = json.load(file)
        logging.info(f"Dataset loaded successfully from {path}")
        return dataset
    except Exception as e:
        logging.error(f"Error loading dataset from {path}: {e}")
        raise

# Download PDF
def download_pdf(url, save_path):
    try:
        response = requests.get(url, verify=certifi.where())
        response.raise_for_status()
        with open(save_path, 'wb') as file:
            file.write(response.content)
        logging.info(f"Downloaded {url} successfully.")
    except requests.exceptions.SSLError as e:
        logging.error(f"SSL Error when downloading {url}: {e}")
        raise
    except requests.exceptions.RequestException as e:
        logging.error(f"Error downloading {url}: {e}")
        raise

# Extract text from PDF
def extract_text_from_pdf(pdf_path):
    try:
        return extract_text(pdf_path)
    except Exception as e:
        logging.error(f"Error extracting text from {pdf_path}: {e}")
        raise

# Determine document length category
def get_document_length_category(text):
    num_words = len(text.split())
    if num_words < 1000:
        return 'short'
    elif num_words < 5000:
        return 'medium'
    else:
        return 'long'

# Custom summarization function
def custom_summarize(text, length_category):
    sentences = text.split('.')
    word_freq = Counter(text.lower().split())
    
    def sentence_score(sentence):
        return sum(word_freq[word.lower()] for word in sentence.split())
    
    scored_sentences = [(sentence, sentence_score(sentence)) for sentence in sentences]
    scored_sentences.sort(key=lambda x: x[1], reverse=True)
    
    if length_category == 'short':
        summary_length = len(sentences) // 3
    elif length_category == 'medium':
        summary_length = len(sentences) // 4
    else:
        summary_length = len(sentences) // 5
    
    summary = '. '.join(sentence for sentence, score in scored_sentences[:summary_length])
    return summary

# Custom TF-IDF implementation
def custom_tfidf(text, max_keywords=10):
    words = text.lower().split()
    word_freq = Counter(words)
    num_words = len(words)
    
    tfidf_scores = {}
    for word, freq in word_freq.items():
        tf = freq / num_words
        idf = math.log(1 + (1 / (freq / num_words)))
        tfidf_scores[word] = tf * idf
    
    sorted_words = sorted(tfidf_scores.items(), key=lambda x: x[1], reverse=True)
    return [word for word, score in sorted_words[:max_keywords]]

# Domain-specific processing
def domain_specific_processing(text, domain):
    # Add domain-specific logic here
    # For example, if the domain is 'medical', we might prioritize medical terms
    if domain == 'medical':
        medical_terms = ['patient', 'diagnosis', 'treatment', 'symptoms', 'medicine']
        return [word for word in text.lower().split() if word in medical_terms]
    return []

# Process individual document
def process_document(name, url, domain='general'):
    start_time = time.time()
    try:
        # Download PDF
        pdf_path = f'temp_{name}.pdf'
        download_pdf(url, pdf_path)

        # Extract text
        text = extract_text_from_pdf(pdf_path)

        # Determine document length
        length_category = get_document_length_category(text)

        # Generate summary
        summary = custom_summarize(text, length_category)

        # Extract keywords
        keywords = custom_tfidf(text)

        # Apply domain-specific processing
        domain_specific_keywords = domain_specific_processing(text, domain)

        # Update MongoDB
        document = {
            "name": name,
            "url": url,
            "length_category": length_category,
            "summary": summary,
            "keywords": keywords,
            "domain_specific_keywords": domain_specific_keywords,
            "processing_time": time.time() - start_time
        }
        collection.update_one({"name": name}, {"$set": document}, upsert=True)

        logging.info(f"Document {name} processed and stored in MongoDB in {time.time() - start_time:.2f} seconds.")

        # Clean up temporary PDF file
        os.remove(pdf_path)
    
    except Exception as e:
        logging.error(f"Error processing document {name}: {e}")
        # Implement error recovery mechanism
        error_doc = {
            "name": name,
            "url": url,
            "error": str(e),
            "processing_time": time.time() - start_time
        }
        collection.update_one({"name": name}, {"$set": error_doc}, upsert=True)


# Process all documents
def process_all_documents(dataset):
    start_time = time.time()
    with multiprocessing.Pool() as pool:
        pool.starmap(process_document, dataset.items())
    total_time = time.time() - start_time
    logging.info(f"All documents processed in {total_time:.2f} seconds.")
    return total_time

# Generate performance report
def generate_performance_report():
    try:
        total_docs = collection.count_documents({})
        successful_docs = collection.count_documents({"error": {"$exists": False}})
        failed_docs = total_docs - successful_docs
        total_time = sum(doc.get('processing_time', 0) for doc in collection.find())
        avg_time = total_time / total_docs if total_docs > 0 else 0

        report = {
            "total_documents": total_docs,
            "successful_documents": successful_docs,
            "failed_documents": failed_docs,
            "total_processing_time": total_time,
            "average_processing_time": avg_time
        }

        collection.update_one(
            {"name": "performance_report"},
            {"$set": report},
            upsert=True
        )
        logging.info("Performance report generated and stored in MongoDB.")
    except Exception as e:
        logging.error(f"Error generating performance report: {e}")

if __name__ == "__main__":
    try:
        # Load dataset
        dataset = load_dataset(DATASET_PATH)

        # Process all documents
        total_processing_time = process_all_documents(dataset)

        # Generate performance report
        generate_performance_report()

        logging.info(f"Pipeline completed. Total processing time: {total_processing_time:.2f} seconds.")
    except Exception as e:
        logging.error(f"Pipeline failed: {e}")