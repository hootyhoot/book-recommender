# Software Requirements

## Table of Contents
1. [Introduction](#1-introduction)
2. [Functional Requirements](#2-functional-requirements)
3. [Non-Functional Requirements](#3-non-functional-requirements)

## 1. Introduction

### 1.1 Purpose
This document outlines the software requirements for an interactive Book Recommendation System. The system aims to provide book recommendations based on user input, either by description or by similar book titles.

### 1.2 Scope
The Book Recommendation will allow users to interact with a book database, receive personalized book recommendations, and explore new reading options based on their preferences or interests.

## 2. Functional Requirements

### 2.1 User Interface
| ID | Requirement |
|----|-------------|
| 2.1.1 | The system shall display a menu with the following options: 1) Recommend by description, 2) Recommend by title |
| 2.1.2 | The system shall display a query text input field for the user to enter the title or description |
| 2.1.3 | The system shall include a submit button to send the query to the system |

### 2.2 Recommendation by Description
| ID | Requirement |
|----|-------------|
| 2.2.1 | The system shall accept a text description from the user |
| 2.2.2 | The system shall process the description using embeddings |
| 2.2.3 | The system shall return a list of book recommendations based on the processed description |

### 2.3 Recommendation by Title
| ID | Requirement |
|----|-------------|
| 2.3.1 | The system shall accept a book title from the user |
| 2.3.2 | The system shall find the title in the database |
| 2.3.3 | The system shall return a list of book recommendations based on the title entered |
| 2.3.4 | The system shall return a list of similar books if an exact match is not found|

### 2.4 Display Recommendations
| ID | Requirement |
|----|-------------|
| 2.4.1 | The system shall display recommended books in a tabular format |
| 2.4.2 | Displayed information shall include: Book Title, Author, Average Rating, URL |

### 2.5 Program Flow
| ID | Requirement |
|----|-------------|
| 2.5.1 | The system should stay on the recommendations page unless the user submits another query|

## 3. Non-Functional Requirements

### 3.1 Performance
| ID | Requirement |
|----|-------------|
| 3.1.1 | The system shall provide recommendations within a reasonable time frame (< 5 seconds) |

### 3.2 Reliability
| ID | Requirement |
|----|-------------|
| 3.2.1 | The system shall handle potential errors (e.g., network issues, file not found) gracefully |

### 3.3 Usability
| ID | Requirement |
|----|-------------|
| 3.3.1 | The system shall provide the recommendations in a clear and intuitive manner |
| 3.3.2 | The system shall have a simple and intuitive web interface |

### 3.4 Maintainability
| ID | Requirement |
|----|-------------|
| 3.4.1 | The code shall be well-documented and follow Python best practices |
| 3.4.2 | The system shall be modular to allow for easy updates and extensions |

### 3.5 Security
| ID | Requirement |
|----|-------------|
| 3.5.1 | API keys shall be stored securely and not hardcoded in the script |

### 3.6 Scalability
| ID | Requirement |
|----|-------------|
| 3.6.1 | The system should be able to handle a growing database of books without significant performance degradation |

### 3.7 Extensibility
| ID | Requirement |
|----|-------------|
| 3.7.1 | The system should be designed to allow easy addition of new recommendation algorithms or data sources |

### 3.8 Dependencies
| ID | Requirement |
|----|-------------|
| 3.8.1 | The system shall require an internet connection for generating embeddings via OpenAI API |
| 3.8.2 | The system shall require a pre-embedded vector database containing the bookdata and embeddings |

